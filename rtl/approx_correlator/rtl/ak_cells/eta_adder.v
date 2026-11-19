// ApproxKit: ETA-I-style adder; 1 <= K <= N-1
// Bit-accurate to approxkit.ETA (see README). Verilog-2001, no vendor primitives.
module eta_adder #(parameter N = 8, parameter K = 3) (input [N-1:0] a, b, output [N:0] y);
  // c[j] = a '1,1' pair exists at some bit >= j of the lower part (scan from MSB)
  wire [K:0]   c;
  wire [K-1:0] lo;
  assign c[K] = 1'b0;
  genvar j;
  generate for (j = K-1; j >= 0; j = j - 1) begin : g
    assign c[j]  = c[j+1] | (a[j] & b[j]);
    assign lo[j] = c[j+1] | (a[j] & b[j]) | (a[j] ^ b[j]);
  end endgenerate
  wire [N-K:0] hi = {1'b0, a[N-1:K]} + {1'b0, b[N-1:K]};
  assign y = {hi, lo};
endmodule
