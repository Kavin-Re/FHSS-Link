// hop_sync_axil.v - keyed hop engine + beacon resync wrapper with an AXI-lite-style register slave.
// "AXI-lite-style": 32-bit data, AW+W accepted together, one outstanding write and one outstanding read, OKAY/SLVERR responses,
// WSTRB ignored (full-word writes only), no protocol checker / VIP was run against it (see README).
//
// Behaviour
//   * tick  (radio-side pulse, or CTRL.SOFT_TICK): when CTRL.EN and a key is loaded, compute the hop for the engine's slot counter
//     (the engine then increments it).  hop_valid/hop_chan pulse when done.  A tick that arrives while the engine is busy or while
//     a tick is already pending sets STATUS.OVERRUN (sticky); a tick while busy is served late, a second pending tick is dropped.
//   * beacon (beacon_valid + beacon_slot, only when CTRL.BCN_EN): beacon_slot is "the slot index of the NEXT hop".  When the engine is
//     idle the wrapper compares it with the engine's slot counter: equal -> BCN_CNT.lock++, different -> BCN_CNT.drift++ and
//     STATUS.DRIFT (sticky); in both cases the slot counter is (re)loaded with beacon_slot and the since-beacon tick count restarts.
//     A beacon arriving while a previous one is still unapplied replaces it (latest wins).
//   * HOLDOVER: STATUS.LOST = (HOLDOVER != 0) && (ticks since last beacon >= HOLDOVER).
//   * Key words are write-only and may be written only while the engine is idle (otherwise SLVERR, no effect, STATUS.KEYERR sticky).
//     Writing KEY3 marks the key as loaded.  The slot is staged by SLOT_LO then SLOT_HI; the SLOT_HI write requests the load, which is
//     applied when the engine is idle.  SLOT reads return the live slot counter.
// Register map (byte offsets, 32-bit):
//   0x00 CTRL    RW  [0] EN  [1] SOFT_TICK (W1, reads 0)  [2] CLR_STICKY (W1)  [3] CLR_CNT (W1)  [4] BCN_EN
//   0x04 STATUS  RO  [0] busy [1] key_loaded [2] bcn_pend [3] slot_pend [4] tick_pend [5] lost [6] overrun* [7] drift* [8] nokey* [9] keyerr*
//                    [19:16] last channel         (* sticky, cleared by CLR_STICKY)
//   0x08..0x14 KEY0..KEY3  WO (read 0)
//   0x18 SLOT_LO RW(stage / live slot[31:0])   0x1C SLOT_HI RW (stage [23:0] / live slot[55:32])
//   0x20 BCN_CNT RO  [15:0] lock count  [31:16] drift count (both saturate at 0xFFFF)
//   0x24 HOLDOVER RW [15:0]
//   0x28 HOPCNT  RO  hops delivered (wraps)
//   0x2C ID      RO  0x48530001
/* verilator lint_off UNUSEDSIGNAL */
module hop_sync_axil #(
    parameter M   = 13,
    parameter RW  = 32,
    parameter NCH = 2,
    parameter DW  = 64,
    parameter CW  = $clog2(M)
)(
    input  wire          clk,
    input  wire          rst_n,
    // AXI-lite-style slave
    input  wire [7:0]    s_awaddr,
    input  wire          s_awvalid,
    output wire          s_awready,
    input  wire [31:0]   s_wdata,
    input  wire [3:0]    s_wstrb,
    input  wire          s_wvalid,
    output wire          s_wready,
    output reg  [1:0]    s_bresp,
    output reg           s_bvalid,
    input  wire          s_bready,
    input  wire [7:0]    s_araddr,
    input  wire          s_arvalid,
    output wire          s_arready,
    output reg  [31:0]   s_rdata,
    output reg  [1:0]    s_rresp,
    output reg           s_rvalid,
    input  wire          s_rready,
    // radio side
    input  wire          tick,
    input  wire          beacon_valid,
    input  wire [55:0]   beacon_slot,
    output wire          hop_valid,
    output wire [CW-1:0] hop_chan
);
    localparam [7:0] A_CTRL = 8'h00, A_STATUS = 8'h04, A_KEY0 = 8'h08, A_KEY1 = 8'h0C, A_KEY2 = 8'h10, A_KEY3 = 8'h14,
                     A_SLO = 8'h18, A_SHI = 8'h1C, A_BCN = 8'h20, A_HOLD = 8'h24, A_HOPC = 8'h28, A_ID = 8'h2C;

    // ---------------- engine ----------------
    wire         busy;
    wire [55:0]  slot_cur;
    wire         ev;
    wire [CW-1:0] ec;
    reg  [3:0]   e_key_we;
    reg  [31:0]  e_key_word;
    reg          e_slot_we;
    reg  [55:0]  e_slot_in;
    reg          e_req;
    hop_keyed_lean #(.M(M), .RW(RW), .NCH(NCH), .DW(DW)) u_eng (
        .clk(clk), .rst_n(rst_n), .key_in({4{e_key_word}}), .key_we(e_key_we), .slot_in(e_slot_in), .slot_we(e_slot_we),
        .req(e_req), .busy(busy), .valid(ev), .chan(ec), .slot_cur(slot_cur));
    assign hop_valid = ev;
    assign hop_chan  = ec;

    // ---------------- registers ----------------
    reg         en, bcn_en, key_loaded;
    reg         tick_pend, slot_pend, bcn_pend;
    reg [55:0]  slot_stage, bcn_slot_q;
    reg         st_overrun, st_drift, st_nokey, st_keyerr;
    reg [15:0]  lock_cnt, drift_cnt, holdover, since_bcn;
    reg [31:0]  hopcnt;
    reg [3:0]   chan_last;

    wire lost = (holdover != 16'd0) && (since_bcn >= holdover);

    // ---------------- AXI-lite slave ----------------
    wire wfire = s_awvalid && s_wvalid && !s_bvalid;
    assign s_awready = wfire;
    assign s_wready  = wfire;
    wire rfire = s_arvalid && !s_rvalid;
    assign s_arready = rfire;

    wire w_key = (s_awaddr == A_KEY0) || (s_awaddr == A_KEY1) || (s_awaddr == A_KEY2) || (s_awaddr == A_KEY3);
    wire w_ok  = (s_awaddr == A_CTRL) || w_key || (s_awaddr == A_SLO) || (s_awaddr == A_SHI) || (s_awaddr == A_HOLD);
    wire r_ok  = (s_araddr == A_CTRL) || (s_araddr == A_STATUS) || (s_araddr == A_KEY0) || (s_araddr == A_KEY1) || (s_araddr == A_KEY2) ||
                 (s_araddr == A_KEY3) || (s_araddr == A_SLO) || (s_araddr == A_SHI) || (s_araddr == A_BCN) || (s_araddr == A_HOLD) ||
                 (s_araddr == A_HOPC) || (s_araddr == A_ID);
    wire key_blocked = w_key && busy;                         // key words only while the engine is idle

    wire [31:0] status = {12'd0, chan_last, 6'd0, st_keyerr, st_nokey, st_drift, st_overrun, lost, tick_pend, slot_pend, bcn_pend,
                          key_loaded, busy};
    reg  [31:0] rd_mux;
    always @* begin
        case (s_araddr)
        A_CTRL:   rd_mux = {27'd0, bcn_en, 3'd0, en};
        A_STATUS: rd_mux = status;
        A_SLO:    rd_mux = slot_cur[31:0];
        A_SHI:    rd_mux = {8'd0, slot_cur[55:32]};
        A_BCN:    rd_mux = {drift_cnt, lock_cnt};
        A_HOLD:   rd_mux = {16'd0, holdover};
        A_HOPC:   rd_mux = hopcnt;
        A_ID:     rd_mux = 32'h48530001;
        default:  rd_mux = 32'd0;                              // KEY0..3 read as 0 (the key is never readable)
        endcase
    end

    // ---------------- arbitration of engine actions (combinational, only when the engine is idle) ----------------
    wire do_slot = !busy && slot_pend;
    wire do_bcn  = !busy && bcn_pend && !slot_pend;
    wire do_req  = !busy && tick_pend && en && key_loaded && !slot_pend && !bcn_pend;
    always @* begin
        e_key_we   = 4'd0;
        e_key_word = s_wdata;
        if (wfire && w_key && !busy) begin
            case (s_awaddr)
            A_KEY0: e_key_we = 4'b0001;
            A_KEY1: e_key_we = 4'b0010;
            A_KEY2: e_key_we = 4'b0100;
            default: e_key_we = 4'b1000;
            endcase
        end
        e_slot_we = do_slot || do_bcn;
        e_slot_in = do_slot ? slot_stage : bcn_slot_q;
        e_req     = do_req;
    end

    wire soft_tick = wfire && (s_awaddr == A_CTRL) && s_wdata[1];
    // 'en' as seen by this tick: a CTRL write that sets EN in the same cycle as a soft tick counts
    wire en_next   = (wfire && (s_awaddr == A_CTRL)) ? s_wdata[0] : en;
    wire tick_in   = (tick || soft_tick) && en_next;

    always @(posedge clk) begin
        s_bvalid <= s_bvalid && !s_bready;
        s_rvalid <= s_rvalid && !s_rready;
        if (!rst_n) begin
            en <= 1'b0; bcn_en <= 1'b0; key_loaded <= 1'b0; tick_pend <= 1'b0; slot_pend <= 1'b0; bcn_pend <= 1'b0;
            st_overrun <= 1'b0; st_drift <= 1'b0; st_nokey <= 1'b0; st_keyerr <= 1'b0;
            lock_cnt <= 16'd0; drift_cnt <= 16'd0; holdover <= 16'd0; since_bcn <= 16'd0; hopcnt <= 32'd0; chan_last <= 4'd0;
            slot_stage <= 56'd0; bcn_slot_q <= 56'd0;
            s_bvalid <= 1'b0; s_rvalid <= 1'b0; s_bresp <= 2'b00; s_rresp <= 2'b00; s_rdata <= 32'd0;
        end else begin
            // ---- AXI reads ----
            if (rfire) begin s_rvalid <= 1'b1; s_rdata <= r_ok ? rd_mux : 32'd0; s_rresp <= r_ok ? 2'b00 : 2'b10; end
            // ---- AXI writes ----
            if (wfire) begin
                s_bvalid <= 1'b1; s_bresp <= (!w_ok || key_blocked) ? 2'b10 : 2'b00;
                if (w_ok && !key_blocked) begin
                    case (s_awaddr)
                    A_CTRL: begin
                        en <= s_wdata[0]; bcn_en <= s_wdata[4];
                        if (s_wdata[2]) begin st_overrun <= 1'b0; st_drift <= 1'b0; st_nokey <= 1'b0; st_keyerr <= 1'b0; end
                        if (s_wdata[3]) begin lock_cnt <= 16'd0; drift_cnt <= 16'd0; hopcnt <= 32'd0; end
                    end
                    A_KEY3: key_loaded <= 1'b1;
                    A_SLO:  slot_stage[31:0] <= s_wdata;
                    A_SHI:  begin slot_stage[55:32] <= s_wdata[23:0]; slot_pend <= 1'b1; end
                    A_HOLD: holdover <= s_wdata[15:0];
                    default: ;
                    endcase
                end
                if (key_blocked) st_keyerr <= 1'b1;
            end
            // engine actions retire their pending flags first; new events below may re-set them in the same clock
            if (do_slot) slot_pend <= 1'b0;
            if (do_bcn) begin
                bcn_pend <= 1'b0;
                if (bcn_slot_q == slot_cur) begin if (lock_cnt != 16'hFFFF) lock_cnt <= lock_cnt + 16'd1; end
                else begin if (drift_cnt != 16'hFFFF) drift_cnt <= drift_cnt + 16'd1; st_drift <= 1'b1; end
            end
            if (do_req) tick_pend <= 1'b0;
            // ---- radio side events (hardware events override the sticky clears above) ----
            if (tick_in) begin
                if (!key_loaded) st_nokey <= 1'b1;
                else begin
                    if (busy || tick_pend) st_overrun <= 1'b1;
                    tick_pend <= 1'b1;
                end
                if (since_bcn != 16'hFFFF) since_bcn <= since_bcn + 16'd1;
            end
            if (beacon_valid && bcn_en) begin
                bcn_pend <= 1'b1; bcn_slot_q <= beacon_slot; since_bcn <= 16'd0;
            end
            if (ev) begin hopcnt <= hopcnt + 32'd1; chan_last <= ec; end
        end
    end

`ifdef FORMAL
    reg f_init = 1'b1;
    always @(posedge clk) f_init <= 1'b0;
    always @* if (f_init) assume(!rst_n);
    always @(posedge clk) if (!f_init) begin
        assert(!(do_slot && do_bcn));                         // one engine action per clock
        assert(!(do_req && (do_slot || do_bcn)));
        assert(!(|e_key_we) || !busy);                        // key words only while idle
        assert(!(e_slot_we && e_req));
        if (hop_valid) assert(hop_chan < M);
        assert(!(s_bvalid && s_bresp == 2'b01));              // only OKAY / SLVERR are ever issued
        assert(!(s_rvalid && s_rresp == 2'b01));
        if (s_rvalid && s_rresp == 2'b10) assert(s_rdata == 32'd0);
    end
    // a hop is only requested with a key loaded and EN set
    always @(posedge clk) if (!f_init && e_req) assert(key_loaded && en);
    always @(posedge clk) cover(!f_init && hop_valid);
    always @(posedge clk) cover(!f_init && do_bcn && bcn_slot_q != slot_cur);          // a drift resync is reachable
    always @(posedge clk) cover(!f_init && st_overrun);
`endif
endmodule
