// corr_mode_ctrl.v - exact/approximate mode controller driven by the 2-bit ladder state (sim/ladder.py: 0 NORMAL, 1 ADAPT, 2 CODED, 3 SURVIVAL).
// Policy (as in lab5/approx_correlator.py): approximate adders in NORMAL/ADAPT, exact in CODED/SURVIVAL  -> want_exact = ladder[1].
// The mode only changes on frame_tick (a frame boundary), so a frame is processed entirely in one mode (no mid-frame switch):
//   ST_APPROX : ex_q = 0.  ladder wants exact at a frame boundary -> ST_EXACT
//   ST_EXACT  : ex_q = 1.  ladder allows approximate at a frame boundary -> ST_COOL (counting)
//   ST_COOL   : ex_q = 1, hysteresis: after DWELL consecutive frames that allow approximate -> ST_APPROX; any 'wants exact' -> ST_EXACT
// ex_q is its own flop (never a decode of the state), so it cannot glitch from the state decode.  Reset state: ST_EXACT (safe).
/* verilator lint_off UNUSEDSIGNAL */
module corr_mode_ctrl #(parameter DWELL = 8, parameter CWID = 4) (
    input  wire       clk, rst_n,
    input  wire [1:0] ladder,
    input  wire       frame_tick,
    output reg        ex_q
);
    localparam [1:0] ST_APPROX = 2'd0, ST_EXACT = 2'd1, ST_COOL = 2'd2;
    reg [1:0]      st;
    reg [CWID-1:0] cnt;
    wire want_exact = ladder[1];
    always @(posedge clk) begin
        if (!rst_n) begin st <= ST_EXACT; cnt <= {CWID{1'b0}}; ex_q <= 1'b1; end
        else if (frame_tick) begin
            case (st)
            ST_APPROX: if (want_exact) begin st <= ST_EXACT; ex_q <= 1'b1; end
            ST_EXACT:  if (!want_exact) begin st <= ST_COOL; cnt <= 1; end
            ST_COOL:   if (want_exact) st <= ST_EXACT;
                       else if (cnt == DWELL - 1) begin st <= ST_APPROX; ex_q <= 1'b0; cnt <= {CWID{1'b0}}; end
                       else cnt <= cnt + 1'b1;
            default:   begin st <= ST_EXACT; ex_q <= 1'b1; end
            endcase
        end
    end
`ifdef FORMAL
    reg f_init = 1'b1; reg f_pex = 1'b0; reg f_ptick = 1'b0;
    always @(posedge clk) begin f_init <= 1'b0; f_pex <= ex_q; f_ptick <= frame_tick; end
    always @* if (f_init) assume(!rst_n);
    always @(posedge clk) if (!f_init) begin
        assert(st <= ST_COOL);                                  // no illegal FSM state
        assert(cnt < DWELL);                                    // dwell counter bounded
        assert(ex_q == (st != ST_APPROX));                      // ex_q always agrees with the state
        if (rst_n && !f_ptick && !$past(!rst_n)) assert(ex_q == f_pex);   // ex_q changes only in the clock after a frame_tick (or reset)
        if (st == ST_COOL) assert(cnt != 0);
    end
    always @(posedge clk) cover(!f_init && st == ST_APPROX);
    always @(posedge clk) cover(!f_init && st == ST_COOL && ex_q);
    always @(posedge clk) cover(!f_init && f_pex && !ex_q);      // switch exact -> approximate happens
    always @(posedge clk) cover(!f_init && !f_pex && ex_q);      // switch approximate -> exact happens
`endif
endmodule
