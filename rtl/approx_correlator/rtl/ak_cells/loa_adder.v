// ApproxKit: lower-part-OR adder; requires 1 <= K <= N-1
// Bit-accurate to approxkit.LOA (see README). Verilog-2001, no vendor primitives.
module loa_adder #(parameter N = 8, parameter K = 3) (input [N-1:0] a, b, output [N:0] y);
  wire [K-1:0]   lo  = a[K-1:0] | b[K-1:0];
  wire           cin = a[K-1] & b[K-1];
  wire [N-K:0]   hi  = {1'b0, a[N-1:K]} + {1'b0, b[N-1:K]} + cin;
  assign y = {hi, lo};
endmodule
