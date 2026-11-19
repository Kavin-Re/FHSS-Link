// Self-checking testbench: RTL hop_lfsr vs Python (4 seeds x 20000 hops; seed 0 is mapped to 1).
`timescale 1ns/1ps
module tb_hop_lfsr;
    reg clk = 0, rst_n = 0; reg [15:0] seed_in; reg seed_we = 0, req = 0;
    wire valid; wire [3:0] chan;
    hop_lfsr #(.M(13)) dut (.clk(clk), .rst_n(rst_n), .seed_in(seed_in), .seed_we(seed_we), .req(req), .valid(valid), .chan(chan));
    always #5 clk = ~clk;
    reg [7:0] vec [0:79999]; reg [15:0] seeds [0:3];
    integer k, i, errs, fd, cyc, cmax;
    initial begin
        $readmemh({`VDIR, "vec_lfsr.mem"}, vec); $readmemh({`VDIR, "seeds_lfsr.mem"}, seeds);
        fd = $fopen({`ODIR, "rtl_stream_lfsr.txt"}, "w"); errs = 0; cmax = 0;
        repeat (3) @(posedge clk); rst_n = 1; repeat (2) @(posedge clk);
        for (k = 0; k < 4; k = k + 1) begin
            @(negedge clk); seed_in = seeds[k]; seed_we = 1; @(negedge clk); seed_we = 0;
            for (i = 0; i < 20000; i = i + 1) begin
                req = 1; cyc = 0; @(negedge clk); req = 0;
                while (!valid) begin @(negedge clk); cyc = cyc + 1; end
                cyc = cyc + 1; if (cyc > cmax) cmax = cyc;
                if (chan !== vec[k*20000 + i][3:0]) begin errs = errs + 1; if (errs < 10) $display("MISMATCH k=%0d i=%0d rtl=%0d exp=%0d", k, i, chan, vec[k*20000+i]); end
                if (k == 0) $fwrite(fd, "%0d\n", chan);
            end
        end
        $fclose(fd);
        $display("TB[lfsr] hops=80000 errs=%0d max cycles req->valid=%0d", errs, cmax);
        if (errs == 0) $display("RESULT lfsr PASS"); else $display("RESULT lfsr FAIL");
        $finish;
    end
endmodule
