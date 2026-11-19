// ApproxKit: truncated adder (low K result bits = 0); 1 <= K <= N-1
// Bit-accurate to approxkit.TruncatedAdder (see README). Verilog-2001, no vendor primitives.
module trunc_adder #(parameter N = 8, parameter K = 3) (input [N-1:0] a, b, output [N:0] y);
  wire [N-K:0] hi = {1'b0, a[N-1:K]} + {1'b0, b[N-1:K]};
  assign y = {hi, {K{1'b0}}};
endmodule
