// hop_keyed_lean.v - op-serialised keyed hop engine (SipHash-2-4 + Lemire), functionally identical to rtl/hop_engine/rtl/hop_keyed.v.
// Verilog-2001 subset (iverilog / verilator / yosys).
//
// v1 evaluates a whole SipRound (4 x 64-bit adders) per clock.  Here ONE adder is shared by the four add-ops of a round:
//   op0: v0+=v1 ; v1=rotl13(v1)^v0 ; v0=rotl32(v0)        op1: v2+=v3 ; v3=rotl16(v3)^v2
//   op2: v0+=v3 ; v3=rotl21(v3)^v0                         op3: v2+=v1 ; v1=rotl17(v1)^v2 ; v2=rotl32(v2)
// DW = 64 : one 64-bit adder, one op per clock          -> 4 clocks per round, 36 clocks req->valid
// DW = 32 : one 32-bit adder + carry flop, two clocks/op -> 8 clocks per round, 68 clocks req->valid
// (v1 for comparison: 4 adders, 12 clocks req->valid.)  DW=32 writes the low half of the adder's destination register in the
// first clock (the destination is always overwritten by the op, so no extra 32-bit sum register is needed) and finishes in the second.
// Interface is the same as hop_keyed except that key_we is 4 bits (one per 32-bit key word) (key_in/key_we, slot_in/slot_we only while idle, req pulse, valid 1-clk pulse with chan),
// plus slot_cur (read-only view of the internal slot counter, no logic).
/* verilator lint_off UNUSEDSIGNAL */
module hop_keyed_lean #(
    parameter M   = 13,
    parameter RW  = 32,
    parameter NCH = 2,
    parameter DW  = 64,           // 64 or 32
    parameter CW  = $clog2(M)
)(
    input  wire          clk,
    input  wire          rst_n,   // synchronous, active low (control state only)
    input  wire [127:0]  key_in,
    input  wire [3:0]    key_we,   // per 32-bit word write enables (tie all four together for a whole-key load)
    input  wire [55:0]   slot_in,
    input  wire          slot_we,
    input  wire          req,
    output wire          busy,
    output reg           valid,
    output reg  [CW-1:0] chan,
    output wire [55:0]   slot_cur
);
    localparam [2:0] S_IDLE = 3'd0, S_LOAD = 3'd1, S_RND = 3'd2, S_FIN = 3'd3, S_RED = 3'd4;
    localparam [63:0] C0 = 64'h736f6d6570736575, C1 = 64'h646f72616e646f6d,
                      C2 = 64'h6c7967656e657261, C3 = 64'h7465646279746573;
    localparam [63:0] BLK = 64'h0800000000000000;
    localparam [RW:0]   TWO_RW = {1'b1, {RW{1'b0}}};
    localparam [RW:0]   THR = TWO_RW % M;
    localparam          SER = (DW == 32);

    reg [127:0] key_r;
    reg [55:0]  slot_r;
    reg [7:0]   retry;
    reg [2:0]   state;
    reg [2:0]   rnd;              // round index 0..7
    reg [1:0]   op;               // add-op index within the round
    reg         half;             // DW=32: 0 = low half clock, 1 = high half clock (always 0 for DW=64)
    reg         cy;               // DW=32: carry between the halves
    reg [1:0]   cnt;
    reg [63:0]  v0, v1, v2, v3;

    wire [63:0] msg = {retry, slot_r};
    assign busy = (state != S_IDLE);
    assign slot_cur = slot_r;

    // ---- shared adder ----
    wire [63:0] X = op[0] ? v2 : v0;
    wire [63:0] Y = (op[0] ^ op[1]) ? v3 : v1;
    wire [63:0] s;
    wire [32:0] s32;
    generate if (SER) begin : g_ser
        wire [31:0] xa = half ? X[63:32] : X[31:0];
        wire [31:0] ya = half ? Y[63:32] : Y[31:0];
        assign s32 = {1'b0, xa} + {1'b0, ya} + {32'd0, (half & cy)};
        assign s   = {s32[31:0], X[31:0]};          // valid in the high-half clock: X[31:0] already holds the low sum
    end else begin : g_par
        assign s32 = 33'd0;
        assign s   = X + Y;
    end endgenerate

    wire [63:0] rot13v1 = {v1[50:0], v1[63:51]};
    wire [63:0] rot17v1 = {v1[46:0], v1[63:47]};
    wire [63:0] rot16v3 = {v3[47:0], v3[63:48]};
    wire [63:0] rot21v3 = {v3[42:0], v3[63:43]};
    wire [63:0] rot32s  = {s[31:0], s[63:32]};
    wire        fin_clk = (!SER) || half;            // clock in which the full 64-bit sum is available
    wire        last_op = (op == 2'd3) && fin_clk;

    // ---- Lemire reduction of the low RW bits of v0 ----
    wire [RW-1:0]      x    = v0[RW-1:0];
    localparam [CW:0]  MC   = M;
    wire [RW+CW:0]     prod = x * MC;
    wire [RW-1:0]      lo   = prod[RW-1:0];
    wire [CW-1:0]      hi   = prod[RW+CW-1:RW];
    wire               acc  = ({1'b0, lo} >= THR);

    always @(posedge clk) begin
        valid <= 1'b0;
        if (key_we[0]) key_r[31:0]   <= key_in[31:0];
        if (key_we[1]) key_r[63:32]  <= key_in[63:32];
        if (key_we[2]) key_r[95:64]  <= key_in[95:64];
        if (key_we[3]) key_r[127:96] <= key_in[127:96];
        if (slot_we) slot_r <= slot_in;
        if (!rst_n) begin
            state <= S_IDLE;
        end else begin
            case (state)
            S_IDLE: if (req) begin retry <= 8'd0; state <= S_LOAD; end
            S_LOAD: begin
                v0 <= key_r[63:0]   ^ C0;
                v1 <= key_r[127:64] ^ C1;
                v2 <= key_r[63:0]   ^ C2;
                v3 <= key_r[127:64] ^ C3 ^ msg;
                rnd <= 3'd0; op <= 2'd0; half <= 1'b0; cy <= 1'b0; state <= S_RND;
            end
            S_RND: begin
                if (SER && !half) begin                  // low-half clock: write low sum into the adder's destination, keep carry
                    if (op[0]) v2[31:0] <= s32[31:0]; else v0[31:0] <= s32[31:0];
                    cy <= s32[32]; half <= 1'b1;
                end else begin
                    half <= 1'b0; op <= op + 2'd1;
                    case (op)
                    2'd0: begin v0 <= rot32s; v1 <= rot13v1 ^ s; end
                    2'd1: begin v2 <= s;      v3 <= rot16v3 ^ s; end
                    2'd2: begin v0 <= s;      v3 <= rot21v3 ^ s; end
                    default: begin
                        v2 <= rot32s ^ ((rnd == 3'd3) ? 64'hff : 64'd0);
                        v1 <= rot17v1 ^ s;
                        v0 <= v0 ^ ((rnd == 3'd1) ? msg : (rnd == 3'd3) ? BLK : 64'd0);
                        v3 <= v3 ^ ((rnd == 3'd1) ? BLK : 64'd0);
                    end
                    endcase
                    if (last_op) begin
                        rnd <= rnd + 3'd1;
                        if (rnd == 3'd7) state <= S_FIN;
                    end
                end
            end
            S_FIN: begin
                v0 <= v0 ^ v1 ^ v2 ^ v3;
                cnt <= 2'd0; state <= S_RED;
            end
            S_RED: begin
                if (acc) begin
                    chan <= hi; valid <= 1'b1; state <= S_IDLE;
                    slot_r <= slot_r + 56'd1;
                end else if (cnt == NCH-1) begin
                    retry <= retry + 8'd1; state <= S_LOAD;
                end else begin
                    v0 <= v0 >> RW; cnt <= cnt + 2'd1;
                end
            end
            default: state <= S_IDLE;
            endcase
        end
    end

`ifdef FORMAL
    reg f_init = 1'b1; reg f_pv = 1'b0; reg [2:0] f_ps = 3'd0; reg [55:0] f_pslot = 56'd0; reg f_pwe = 1'b0;
    always @(posedge clk) begin f_init <= 1'b0; f_pv <= valid; f_ps <= state; f_pslot <= slot_r; f_pwe <= slot_we; end
    always @* if (f_init) assume(!rst_n);
`ifdef FORMAL_ENV
    // standalone proof: protocol obligations on the environment are ASSUMED
    always @* if (busy) assume(!(|key_we) && !slot_we);
    always @* if (busy) assume(!req);
`else
    // wrapper proof: the same protocol obligations are ASSERTED (the wrapper must discharge them)
    always @* if (!f_init && busy) assert(!(|key_we) && !slot_we && !req);
`endif
    always @(posedge clk) if (!f_init) begin
        assert(state <= S_RED);
        if (state == S_RND) begin assert(op <= 2'd3); if (!SER) assert(!half); end
        if (state == S_RED) assert(cnt < NCH);
        if (valid) assert(chan < M);
        assert(!(valid && f_pv));
        if (valid) assert(f_ps == S_RED && state == S_IDLE);
        if (valid) assert(slot_r == f_pslot + 56'd1);
        if (!valid && f_ps != S_RED && !f_pwe) assert(slot_r == f_pslot);
    end
    always @(posedge clk) cover(!f_init && valid && f_ps == S_RED && retry == 8'd0);
`endif
endmodule
