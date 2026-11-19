// ApproxKit: exact ripple-style reference adder (baseline)
// Bit-accurate to approxkit.ExactAdder (see README). Verilog-2001, no vendor primitives.
module exact_adder #(parameter N = 8) (input [N-1:0] a, b, output [N:0] y);
  assign y = {1'b0, a} + {1'b0, b};
endmodule
