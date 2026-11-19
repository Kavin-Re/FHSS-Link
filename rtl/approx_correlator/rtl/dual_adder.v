// dual_adder.v - runtime-switchable adder cell: ex=1 -> exact N-bit adder ({1'b0,a}+{1'b0,b}); ex=0 -> the ApproxKit approximation of the
// same name, bit-identical to rtl/ak_cells/{loa,trunc,eta}_adder.v (checked by simulation and by a yosys SAT miter, see formal/).
// The upper (N-K)-bit adder is shared; only the lower K bits and the carry into the upper part are switched, so the exact mode
// re-uses the same upper adder.  TYPE: 1 = LOA, 2 = truncated, 3 = ETA-I.   Requires 1 <= K <= N-1.
module dual_adder #(parameter N = 8, parameter K = 3, parameter TYPE = 1) (input [N-1:0] a, b, input ex, output [N:0] y);
  wire [K:0]   ls = {1'b0, a[K-1:0]} + {1'b0, b[K-1:0]};     // exact low part with carry-out
  wire [K-1:0] lo_ap;
  wire         cin_ap;
  generate
    if (TYPE == 1) begin : g_loa
      assign lo_ap  = a[K-1:0] | b[K-1:0];
      assign cin_ap = a[K-1] & b[K-1];
    end else if (TYPE == 3) begin : g_eta        // ETA-I: scan from bit K-1 down, once a 1,1 pair is seen all lower bits (and itself) = 1
      reg [K-1:0] lo_r; integer j; reg c;
      always @* begin
        lo_r = {K{1'b0}}; c = 1'b0;
        for (j = K-1; j >= 0; j = j - 1) begin
          lo_r[j] = c | (a[j] & b[j]) | (a[j] ^ b[j]);
          c = c | (a[j] & b[j]);
        end
      end
      assign lo_ap  = lo_r;
      assign cin_ap = 1'b0;
    end else begin : g_trunc                     // truncated: low K bits of the sum forced to 0, no carry into the upper part
      assign lo_ap  = {K{1'b0}};
      assign cin_ap = 1'b0;
    end
  endgenerate
  wire [K-1:0] lo  = ex ? ls[K-1:0] : lo_ap;
  wire         cin = ex ? ls[K]     : cin_ap;
  wire [N-K:0] hi  = {1'b0, a[N-1:K]} + {1'b0, b[N-1:K]} + {{(N-K){1'b0}}, cin};
  assign y = {hi, lo};
endmodule
