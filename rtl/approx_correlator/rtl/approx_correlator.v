// approx_correlator.v - ladder-driven DS-SS despreading correlator (N = 16/32/64 chips, 1-bit chips x W-bit signed samples).
// One frame per in_valid pulse: out_valid (1 clock later) with out_sum = sum_i c_i x_i (signed, SW bits), out_bit = (out_sum >= 0),
// out_ex = the mode that frame was computed in (1 = exact).  The mode comes from corr_mode_ctrl (ladder[1:0]); a ladder change takes
// effect at the NEXT frame boundary, so no frame is ever computed in a mixture of modes.  Latency 1 clock, throughput 1 frame/clock.
module approx_correlator #(
    parameter N = 32, parameter W = 6, parameter ATYPE = 1, parameter K = 3, parameter COMP = 0, parameter DWELL = 8,
    parameter LOGN = $clog2(N),
    parameter SW = W + LOGN + 1
)(
    input  wire              clk, rst_n,
    input  wire [1:0]        ladder,
    input  wire              in_valid,
    input  wire [N-1:0]      code,
    input  wire [N*W-1:0]    x,
    output reg               out_valid,
    output reg  [SW-1:0]     out_sum,
    output reg               out_bit,
    output reg               out_ex
);
    wire ex_q;
    corr_mode_ctrl #(.DWELL(DWELL)) u_mode (.clk(clk), .rst_n(rst_n), .ladder(ladder), .frame_tick(in_valid), .ex_q(ex_q));
    wire [SW-1:0] s;
    corr_core #(.N(N), .W(W), .ATYPE(ATYPE), .K(K), .DYN(1), .COMP(COMP)) u_core (.code(code), .x(x), .ex(ex_q), .sum(s));
    always @(posedge clk) begin
        if (!rst_n) begin out_valid <= 1'b0; out_sum <= {SW{1'b0}}; out_bit <= 1'b0; out_ex <= 1'b1; end
        else begin
            out_valid <= in_valid;
            if (in_valid) begin out_sum <= s; out_bit <= ~s[SW-1]; out_ex <= ex_q; end
        end
    end
endmodule
