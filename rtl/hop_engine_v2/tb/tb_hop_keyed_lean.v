// Self-checking testbench: RTL hop_keyed vs Python vectors (model/gen_vectors.py).
// Defines (all required, set by scripts/run_sim.sh): TAG string suffix, M, RW, NCH, NKEY, NSLOT, VDIR path (string literals with trailing "/").
`timescale 1ns/1ps
`ifndef NDIG
`define NDIG 1000
`endif
module tb_hop_keyed_lean;
    parameter CW = $clog2(`M);
    reg clk = 0, rst_n = 0;
    reg [127:0] key_in; reg key_we = 0; wire [3:0] key_we4 = {4{key_we}};
    reg [55:0] slot_in; reg slot_we = 0;
    reg req = 0;
    wire busy, valid; wire [CW-1:0] chan;
    hop_keyed_lean #(.M(`M), .RW(`RW), .NCH(`NCH), .DW(`DW)) dut (.clk(clk), .rst_n(rst_n), .key_in(key_in), .key_we(key_we4),
        .slot_in(slot_in), .slot_we(slot_we), .req(req), .busy(busy), .valid(valid), .chan(chan), .slot_cur());
    always #5 clk = ~clk;

    reg [15:0]  vec  [0:`NKEY*`NSLOT-1];
    reg [63:0]  dig  [0:`NKEY*`NDIG-1];
    reg [127:0] keys [0:`NKEY-1];
    reg [55:0]  strt [0:`NKEY-1];
    integer k, i, errs, dig_errs, dig_checked, ret_errs, ret_seen, cyc, cmin, cmax, ctot, nhop, fd, gap;
    reg [15:0] e;
    integer cur_k, cur_i;

    // digest check: at first reduction cycle of a retry-0 attempt compare v0 against the Python digest
    always @(posedge clk) if (rst_n && dut.state == 3'd4 && dut.cnt == 2'd0 && dut.retry == 8'd0 && cur_i < `NDIG) begin
        dig_checked = dig_checked + 1;
        if (dut.v0 !== dig[cur_k*`NDIG + cur_i]) begin
            dig_errs = dig_errs + 1;
            if (dig_errs < 5) $display("DIGEST MISMATCH k=%0d i=%0d rtl=%h exp=%h", cur_k, cur_i, dut.v0, dig[cur_k*`NDIG + cur_i]);
        end
    end

    initial begin
        $readmemh({`VDIR, "vec_",   `TAG, ".mem"}, vec);
        $readmemh({`VDIR, "dig_",   `TAG, ".mem"}, dig);
        $readmemh({`VDIR, "keys_",  `TAG, ".mem"}, keys);
        $readmemh({`VDIR, "starts_",`TAG, ".mem"}, strt);
        fd = $fopen({`ODIR, "rtl_stream_", `TAG, ".txt"}, "w");
        errs = 0; dig_errs = 0; dig_checked = 0; ret_errs = 0; ret_seen = 0; cmin = 1000; cmax = 0; ctot = 0; nhop = 0; cur_k = 0; cur_i = 100000;
        repeat (4) @(posedge clk); rst_n = 1; repeat (2) @(posedge clk);
        for (k = 0; k < `NKEY; k = k + 1) begin
            cur_k = k;
            @(negedge clk); key_in = keys[k]; key_we = 1; slot_in = strt[k]; slot_we = 1;
            @(negedge clk); key_we = 0; slot_we = 0;
            for (i = 0; i < `NSLOT; i = i + 1) begin
                cur_i = i;
                gap = $random & 3;                                  // random idle gaps
                repeat (gap) @(negedge clk);
                req = 1; cyc = 0; @(negedge clk); req = 0;
                while (!valid) begin @(negedge clk); cyc = cyc + 1; end
                cyc = cyc + 1;
                e = vec[k*`NSLOT + i];
                if (chan !== e[CW-1:0] || e[15:8] !== dut.retry) begin
                    errs = errs + 1;
                    if (errs < 10) $display("MISMATCH k=%0d i=%0d rtl_chan=%0d exp=%0d rtl_retry=%0d exp_retry=%0d", k, i, chan, e[7:0], dut.retry, e[15:8]);
                end
                if (e[15:8] != 0) ret_seen = ret_seen + 1;
                if (chan >= `M) begin errs = errs + 1; $display("OUT OF RANGE %0d", chan); end
                $fwrite(fd, "%0d\n", chan);
                if (e[15:8] == 0) begin if (cyc < cmin) cmin = cyc; if (cyc > cmax) cmax = cyc; ctot = ctot + cyc; nhop = nhop + 1; end
            end
            cur_i = 100000;
        end
        $fclose(fd);
        $display("TB[%s] DW=%0d M=%0d RW=%0d NCH=%0d: hops=%0d chan_errs=%0d digest_checked=%0d digest_errs=%0d hops_with_retry=%0d", `TAG, `DW, `M, `RW, `NCH, `NKEY*`NSLOT, errs, dig_checked, dig_errs, ret_seen);
        $display("TB[%s] cycles req->valid (retry-free hops, req sampled->valid seen): min=%0d max=%0d avg=%0d.%02d", `TAG, cmin, cmax, ctot/nhop, (ctot*100/nhop)%100);
        if (errs == 0 && dig_errs == 0) $display("RESULT %s PASS", `TAG); else $display("RESULT %s FAIL", `TAG);
        $finish;
    end
    initial begin #2000000000; $display("TIMEOUT"); $display("RESULT %s FAIL", `TAG); $finish; end
endmodule
