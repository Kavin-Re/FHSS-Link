// Self-checking testbench: hop_sync_axil driven through its AXI-lite-style slave port + tick/beacon pins, compared with
// model/wrap_model.py (ops in vectors/wrap_{ops,arg,exp}.mem).  Defines: VDIR (string, trailing "/"), DW (engine datapath width), NOPS.
`timescale 1ns/1ps
module tb_hop_sync_axil;
    reg clk = 0, rst_n = 0;
    reg [7:0] awaddr = 0; reg awvalid = 0; wire awready; reg [31:0] wdata = 0; reg wvalid = 0; wire wready;
    wire [1:0] bresp; wire bvalid; reg bready = 0;
    reg [7:0] araddr = 0; reg arvalid = 0; wire arready; wire [31:0] rdata; wire [1:0] rresp; wire rvalid; reg rready = 0;
    reg tick = 0, beacon_valid = 0; reg [55:0] beacon_slot = 0;
    wire hop_valid; wire [3:0] hop_chan;
    hop_sync_axil #(.M(13), .RW(32), .NCH(2), .DW(`DW)) dut (.clk(clk), .rst_n(rst_n),
        .s_awaddr(awaddr), .s_awvalid(awvalid), .s_awready(awready), .s_wdata(wdata), .s_wstrb(4'hF), .s_wvalid(wvalid), .s_wready(wready),
        .s_bresp(bresp), .s_bvalid(bvalid), .s_bready(bready), .s_araddr(araddr), .s_arvalid(arvalid), .s_arready(arready),
        .s_rdata(rdata), .s_rresp(rresp), .s_rvalid(rvalid), .s_rready(rready),
        .tick(tick), .beacon_valid(beacon_valid), .beacon_slot(beacon_slot), .hop_valid(hop_valid), .hop_chan(hop_chan));
    always #5 clk = ~clk;

    reg [7:0]   opc [0:`NOPS-1];
    reg [127:0] arg [0:`NOPS-1];
    reg [63:0]  exp [0:`NOPS-1];
    integer i, errs, nchk, nhops, nwr, nrd, proto_errs, lat_min, lat_max, cyc, d, j, seed;
    reg [1:0] resp; reg [31:0] rdv; reg [3:0] c1, c2; reg got;
    reg [1:0] bresp_hold; reg bv_prev, br_prev;

    // protocol monitor: bvalid/rvalid must stay high with stable response until accepted
    always @(posedge clk) if (rst_n) begin
        if (bv_prev && !br_prev && !(bvalid && bresp == bresp_hold)) begin proto_errs = proto_errs + 1; $display("PROTO: bvalid dropped/changed"); end
        bv_prev <= bvalid; br_prev <= bready; bresp_hold <= bresp;
    end

    task fail; input [255:0] what; begin errs = errs + 1; if (errs < 20) $display("FAIL op#%0d (%0d): %0s", i, opc[i], what); end endtask

    task axi_write; input [7:0] a; input [31:0] data; output [1:0] r; integer w;
        begin
            @(negedge clk); awaddr = a; wdata = data; awvalid = 1; wvalid = 1;
            w = 0;
            #4; while (!(awready && wready) && w < 20) begin @(negedge clk); #4; w = w + 1; end
            @(negedge clk); awvalid = 0; wvalid = 0;
            seed = $random; d = seed & 3;                              // random bready delay (0..3 clocks)
            repeat (d) @(negedge clk);
            bready = 1; #4; while (!bvalid) begin @(negedge clk); #4; end
            r = bresp; @(negedge clk); bready = 0; nwr = nwr + 1;
        end
    endtask
    task axi_read; input [7:0] a; output [31:0] data; output [1:0] r;
        begin
            @(negedge clk); araddr = a; arvalid = 1;
            #4; while (!arready) begin @(negedge clk); #4; end
            @(negedge clk); arvalid = 0;
            seed = $random; d = seed & 3; repeat (d) @(negedge clk);
            rready = 1; #4; while (!rvalid) begin @(negedge clk); #4; end
            data = rdata; r = rresp; @(negedge clk); rready = 0; nrd = nrd + 1;
        end
    endtask
    task pulse_tick; begin @(negedge clk); tick = 1; @(negedge clk); tick = 0; end endtask
    // wait for hop_valid (sampled just before each posedge), up to a limit; got=1 if seen
    task wait_hop; input integer limit; output [3:0] ch; integer w;
        begin
            got = 0; ch = 0; w = 0;
            while (!got && w < limit) begin #4; if (hop_valid) begin got = 1; ch = hop_chan; end @(negedge clk); w = w + 1; end
            if (got) nhops = nhops + 1;
        end
    endtask

    initial begin
        errs = 0; nchk = 0; nhops = 0; nwr = 0; nrd = 0; proto_errs = 0; bv_prev = 0; br_prev = 0; bresp_hold = 0;
        $readmemh({`VDIR, "wrap_ops.mem"}, opc); $readmemh({`VDIR, "wrap_arg.mem"}, arg); $readmemh({`VDIR, "wrap_exp.mem"}, exp);
        repeat (4) @(posedge clk); @(negedge clk); rst_n = 1; repeat (3) @(negedge clk);
        for (i = 0; i < `NOPS; i = i + 1) begin
            case (opc[i])
            1: begin axi_write(arg[i][39:32], arg[i][31:0], resp); nchk = nchk + 1;
                     if (resp !== exp[i][1:0]) fail("bresp"); repeat (3) @(negedge clk); end
            2: begin axi_read(arg[i][7:0], rdv, resp); nchk = nchk + 1;
                     if (resp !== arg[i][33:32]) fail("rresp");
                     if ((rdv & exp[i][63:32]) !== (exp[i][31:0] & exp[i][63:32])) begin fail("rdata");
                        if (errs < 20) $display("   addr=%h got=%h exp=%h", arg[i][7:0], rdv, exp[i][31:0]); end
                     repeat (2) @(negedge clk); end
            3: begin pulse_tick; nchk = nchk + 1;
                     if (exp[i][8]) begin wait_hop(200, c1); if (!got) fail("no hop"); else if (c1 !== exp[i][3:0]) begin fail("chan"); $display("   got=%0d exp=%0d", c1, exp[i][3:0]); end
                          else begin cyc = 0; end end
                     else begin wait_hop(120, c1); if (got) fail("unexpected hop"); end
                     repeat (3) @(negedge clk); end
            4: begin @(negedge clk); beacon_valid = 1; beacon_slot = arg[i][55:0]; @(negedge clk); beacon_valid = 0; beacon_slot = 56'hDEAD_BEEF_00; repeat (4) @(negedge clk); nchk = nchk + 1; end
            5: begin repeat (arg[i][7:0]) @(negedge clk); end
            6: begin pulse_tick; nchk = nchk + 1; repeat (arg[i][127:120] - 1) @(negedge clk);       // beacon while the hop is in flight
                     beacon_valid = 1; beacon_slot = arg[i][55:0]; @(negedge clk); beacon_valid = 0;
                     if (exp[i][8]) begin wait_hop(200, c1); if (!got) fail("no hop(6)"); else if (c1 !== exp[i][3:0]) fail("chan(6)"); end
                     else begin wait_hop(120, c1); if (got) fail("unexpected hop(6)"); end
                     repeat (6) @(negedge clk); end
            7: begin pulse_tick; nchk = nchk + 1; repeat (4) @(negedge clk); pulse_tick;                // second tick while busy
                     if (exp[i][8]) begin
                        wait_hop(200, c1); if (!got) fail("no hop(7a)"); else if (c1 !== exp[i][3:0]) fail("chan(7a)");
                        wait_hop(200, c2); if (!got) fail("no hop(7b)"); else if (c2 !== exp[i][7:4]) fail("chan(7b)");
                     end else begin wait_hop(120, c1); if (got) fail("unexpected hop(7)"); end
                     repeat (6) @(negedge clk); end
            8: begin pulse_tick; nchk = nchk + 1; repeat (2) @(negedge clk);                            // key word write while busy: SLVERR
                     axi_write(8'h08, arg[i][31:0], resp); if (resp !== 2'b10) fail("expected SLVERR on busy key write");
                     wait_hop(200, c1); if (!got) fail("no hop(8)"); else if (c1 !== exp[i][3:0]) fail("chan(8)");
                     repeat (4) @(negedge clk); end
            9: begin axi_write(8'h00, arg[i][31:0], resp); nchk = nchk + 1;                              // CTRL write with SOFT_TICK
                     if (resp !== 2'b00) fail("bresp(soft)");
                     wait_hop(200, c1); if (!got) fail("no hop(9)"); else if (c1 !== exp[i][3:0]) fail("chan(9)");
                     repeat (4) @(negedge clk); end
            default: fail("bad op");
            endcase
        end
        $display("TB[hop_sync_axil DW=%0d] ops=%0d checks=%0d axi_writes=%0d axi_reads=%0d hops_seen=%0d proto_errs=%0d errs=%0d", `DW, `NOPS, nchk, nwr, nrd, nhops, proto_errs, errs);
        if (errs == 0 && proto_errs == 0) $display("RESULT hop_sync_axil_DW%0d PASS", `DW); else $display("RESULT hop_sync_axil_DW%0d FAIL", `DW);
        $finish;
    end
    initial begin #400000000; $display("TIMEOUT"); $display("RESULT hop_sync_axil_DW%0d FAIL", `DW); $finish; end
endmodule
