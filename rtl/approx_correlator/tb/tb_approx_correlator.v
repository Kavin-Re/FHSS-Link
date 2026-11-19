// Self-checking testbench: approx_correlator vs the bit-exact Python model (model/gen_corr_vectors.py).
// Defines: TAG (string), N, ATYPE, K, COMP, NCLK (stimulus lines), NEXP (expected frames), VDIR (string with trailing "/").
`timescale 1ns/1ps
module tb_approx_correlator;
    localparam W = 6, SW = W + $clog2(`N) + 1, SL = 3 + `N + `N * W;
    reg clk = 0, rst_n = 0; reg [1:0] ladder = 0; reg in_valid = 0; reg [`N-1:0] code = 0; reg [`N*W-1:0] x = 0;
    wire out_valid, out_bit, out_ex; wire [SW-1:0] out_sum;
    approx_correlator #(.N(`N), .W(W), .ATYPE(`ATYPE), .K(`K), .COMP(`COMP), .DWELL(8)) dut (.clk(clk), .rst_n(rst_n), .ladder(ladder),
        .in_valid(in_valid), .code(code), .x(x), .out_valid(out_valid), .out_sum(out_sum), .out_bit(out_bit), .out_ex(out_ex));
    always #5 clk = ~clk;
    reg [SL-1:0] stim [0:`NCLK-1];
    reg [SW+1:0] exps [0:`NEXP-1];
    integer i, nexp, errs, n_ex, n_ap, mode_chg, prev_ex, glitch;
    reg [SW+1:0] e;
    // glitch monitor: out_ex / the internal mode flop may only change in the clock after an accepted frame
    reg dut_ex_prev; reg tick_prev;
    initial glitch = 0;
    always @(posedge clk) if (rst_n) begin
        if (dut.ex_q !== dut_ex_prev && !tick_prev) glitch = glitch + 1;
        dut_ex_prev <= dut.ex_q; tick_prev <= in_valid;
    end
    // combinational-glitch probe: ex_q must be stable between clock edges (sampled just before each edge and 1 ns after the previous one)
    reg ex_early; integer comb_glitch; initial comb_glitch = 0;
    always @(posedge clk) begin #1 ex_early = dut.ex_q; end
    always @(negedge clk) if (rst_n && dut.ex_q !== ex_early) comb_glitch = comb_glitch + 1;
    initial begin
        $readmemh({`VDIR, "stim_", `TAG, ".mem"}, stim); $readmemh({`VDIR, "exp_", `TAG, ".mem"}, exps);
        errs = 0; nexp = 0; n_ex = 0; n_ap = 0; mode_chg = 0; prev_ex = 1;
        repeat (3) @(posedge clk); #1 rst_n = 1;
        for (i = 0; i <= `NCLK; i = i + 1) begin
            @(negedge clk);
            if (out_valid) begin                                        // result of the frame accepted one clock ago
                e = exps[nexp];
                if (out_sum !== e[SW-1:0] || out_bit !== e[SW] || out_ex !== e[SW+1]) begin
                    errs = errs + 1; if (errs < 10) $display("MISMATCH frame %0d: sum rtl=%0d exp=%0d ex rtl=%b exp=%b bit rtl=%b exp=%b", nexp, $signed(out_sum), $signed(e[SW-1:0]), out_ex, e[SW+1], out_bit, e[SW]);
                end
                if (out_ex) n_ex = n_ex + 1; else n_ap = n_ap + 1;
                if (out_ex !== prev_ex[0]) mode_chg = mode_chg + 1;
                prev_ex = out_ex; nexp = nexp + 1;
            end
            if (i < `NCLK) begin
                {in_valid, ladder, code, x} = stim[i];
            end else begin in_valid = 0; end
        end
        $display("TB[%s] N=%0d ATYPE=%0d K=%0d COMP=%0d: frames_checked=%0d (expected %0d) errs=%0d exact_frames=%0d approx_frames=%0d mode_changes=%0d ex_change_without_frame_tick=%0d ex_comb_glitches=%0d",
                 `TAG, `N, `ATYPE, `K, `COMP, nexp, `NEXP, errs, n_ex, n_ap, mode_chg, glitch, comb_glitch);
        if (errs == 0 && nexp == `NEXP && glitch == 0 && comb_glitch == 0 && (`ATYPE == 0 || (n_ap > 0 && n_ex > 0))) $display("RESULT %s PASS", `TAG); else $display("RESULT %s FAIL", `TAG);
        $finish;
    end
    initial begin #200000000; $display("TIMEOUT"); $display("RESULT %s FAIL", `TAG); $finish; end
endmodule
