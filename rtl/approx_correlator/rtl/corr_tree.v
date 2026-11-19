// corr_tree.v - balanced binary adder tree of N unsigned W-bit leaves, built recursively from ApproxKit adder cells.
// Node covering N leaves: two sub-trees of N/2 leaves each (first half / second half), then ONE adder of width n = W + log2(N/2)
// producing n+1 bits.  This is the same tree as "level l adds adjacent pairs (2j, 2j+1)" (the Python model's pairing).
// ATYPE 0 exact | 1 LOA | 2 truncated | 3 ETA-I, approximation parameter K (capped at n-1 per adder); DYN=1 uses dual_adder (ex: 1 = exact).
/* verilator lint_off UNUSEDSIGNAL */
module corr_tree #(
    parameter N = 32, parameter W = 6, parameter ATYPE = 1, parameter K = 3, parameter DYN = 0,
    parameter LOGN = $clog2(N)
)(
    input  wire [N*W-1:0]       t,
    input  wire                 ex,
    output wire [W+LOGN-1:0]    s
);
    generate
        if (N == 1) begin : g_leaf
            assign s = t;
        end else begin : g_node
            localparam H  = N / 2;
            localparam L2 = LOGN - 1;
            localparam n  = W + L2;
            localparam ke = (K > n - 1) ? n - 1 : K;
            wire [n-1:0] sa, sb;
            wire [n:0]   y;
            corr_tree #(.N(H), .W(W), .ATYPE(ATYPE), .K(K), .DYN(DYN)) u_a (.t(t[0 +: H*W]),   .ex(ex), .s(sa));
            corr_tree #(.N(H), .W(W), .ATYPE(ATYPE), .K(K), .DYN(DYN)) u_b (.t(t[H*W +: H*W]), .ex(ex), .s(sb));
            if (ATYPE == 0) begin : g_ex       exact_adder #(.N(n)) u (.a(sa), .b(sb), .y(y)); end
            else if (DYN != 0) begin : g_dual  dual_adder #(.N(n), .K(ke), .TYPE(ATYPE)) u (.a(sa), .b(sb), .ex(ex), .y(y)); end
            else if (ATYPE == 1) begin : g_loa loa_adder #(.N(n), .K(ke)) u (.a(sa), .b(sb), .y(y)); end
            else if (ATYPE == 2) begin : g_tr  trunc_adder #(.N(n), .K(ke)) u (.a(sa), .b(sb), .y(y)); end
            else begin : g_eta                 eta_adder #(.N(n), .K(ke)) u (.a(sa), .b(sb), .y(y)); end
            assign s = y;
        end
    endgenerate
endmodule
