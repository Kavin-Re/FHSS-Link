// hop_lfsr_fold.v - 16-bit LFSR hop engine with a folded "state mod 13" (same behaviour as hop_engine/rtl/hop_lfsr.v for M=13).
// LFSR: x^16+x^14+x^13+x^11+1 (Fibonacci, shift right), step first, hop = state mod 13, seed 0 -> 1, reset state 0xACE1, req->valid 1 clock.
// Folding: 2^6 = 64 = -1 (mod 13) so 2^12 = +1.  With sn = a*2^12 + b*2^6 + c (a 4 bit, b,c 6 bit):  sn = a - b + c (mod 13),
//   t = a + c + (63-b) + 2  is congruent to sn (63 = 11 mod 13, +2 compensates) and 2 <= t <= 143 (8 bit).
// FV = 0 : t mod 13 left to the synthesis tool (8-bit constant modulus instead of 16-bit)
// FV = 1 : second fold t = p*64 + q = q - p, then three conditional subtractions (52, 26, 13) - no divider at all
/* verilator lint_off UNUSEDSIGNAL */
module hop_lfsr_fold #(
    parameter FV = 1
)(
    input  wire          clk,
    input  wire          rst_n,
    input  wire [15:0]   seed_in,
    input  wire          seed_we,
    input  wire          req,
    output reg           valid,
    output reg  [3:0]    chan
);
    reg [15:0] s;
    wire       fb = s[0] ^ s[2] ^ s[3] ^ s[5];
    wire [15:0] sn = {fb, s[15:1]};

    wire [7:0] t = {4'd0, sn[15:12]} + {2'd0, sn[5:0]} + {2'd0, ~sn[11:6]} + 8'd2;
    reg  [6:0] u, u1, u2, u3;
    reg  [3:0] md;
    wire [7:0] tmod = t % 8'd13;
    always @* begin
        u  = {1'b0, t[5:0]} + 7'd13 - {5'd0, t[7:6]};
        u1 = (u  >= 7'd52) ? u  - 7'd52 : u;
        u2 = (u1 >= 7'd26) ? u1 - 7'd26 : u1;
        u3 = (u2 >= 7'd13) ? u2 - 7'd13 : u2;
        if (FV == 0) md = tmod[3:0];
        else         md = u3[3:0];
    end

    always @(posedge clk) begin
        valid <= 1'b0;
        if (!rst_n) s <= 16'hACE1;
        else if (seed_we) s <= (seed_in == 16'd0) ? 16'd1 : seed_in;
        else if (req) begin
            s <= sn; chan <= md; valid <= 1'b1;
        end
    end

`ifdef FORMAL
    reg f_init = 1'b1;
    always @(posedge clk) f_init <= 1'b0;
    always @* if (f_init) assume(!rst_n);
    always @(posedge clk) if (!f_init) begin
        assert(s != 16'd0);
        if (valid) assert(chan < 4'd13);
    end
    // combinational equivalence of the fold with the plain modulus, for every 16-bit value (asserted in the same induction step)
    wire [15:0] f_ref = sn % 16'd13;
    always @* assert({12'd0, md} == f_ref);
`endif
endmodule
