// corr_core.v - DS-SS despreading correlator core: S = sum_i c_i * x_i, c_i = +1 (code bit 1) / -1 (code bit 0), x_i signed W-bit samples.
// Combinational balanced adder tree (corr_tree: log2(N) levels, adder at level l has width n = W+l and produces n+1 bits) built from
// ApproxKit adder cells.  Sign handling keeps every tree adder UNSIGNED (the ApproxKit cells are unsigned):
//     u_i = x_i + 2^(W-1)                      (offset binary: flip the sample MSB)
//     t_i = c_i ? u_i : ~u_i                   (W-bit one's complement for c=-1:  t_i = -x_i + 2^(W-1) - 1)
//     T   = sum_i t_i  (tree, the only approximated part) = S + N*2^(W-1) - nneg,   nneg = #(c_i = -1)
//     S   = T + nneg - N*2^(W-1)  [+ COMP when approximate]   (exact popcount + constant, SW-bit two's complement wrap)
// ATYPE: 0 exact, 1 LOA(K), 2 truncated(K), 3 ETA-I(K), applied with the same K to every adder (K capped at n-1 per adder).
// DYN = 1: cells are dual_adder (runtime ex input: 1 = exact); DYN = 0: the ApproxKit cells are instantiated unmodified (ex ignored).
// COMP: signed constant added to S when the tree is approximate (bias compensation, calibrated in the Python model); 0 = off.
module corr_core #(
    parameter N = 32, parameter W = 6, parameter ATYPE = 1, parameter K = 3, parameter DYN = 0, parameter COMP = 0,
    parameter LOGN = $clog2(N),
    parameter SW = W + LOGN + 1
)(
    input  wire [N-1:0]       code,
    input  wire [N*W-1:0]     x,
    input  wire               ex,        // 1 = exact (only used when DYN=1)
    output wire [SW-1:0]      sum
);
    wire [N*W-1:0] tv;
    genvar i;
    generate
        for (i = 0; i < N; i = i + 1) begin : g_in
            wire [W-1:0] xi = x[i*W +: W];
            wire [W-1:0] ui = {~xi[W-1], xi[W-2:0]};
            assign tv[i*W +: W] = code[i] ? ui : ~ui;
        end
    endgenerate
    wire [W+LOGN-1:0] T;
    corr_tree #(.N(N), .W(W), .ATYPE(ATYPE), .K(K), .DYN(DYN)) u_tree (.t(tv), .ex(ex), .s(T));

    reg  [LOGN:0] nneg;
    integer q;
    always @* begin nneg = {(LOGN+1){1'b0}}; for (q = 0; q < N; q = q + 1) nneg = nneg + {{LOGN{1'b0}}, ~code[q]}; end
    localparam [SW-1:0] NPOS = {{(SW-1){1'b0}}, 1'b1} << (LOGN + W - 1);    // N * 2^(W-1)
    localparam [SW-1:0] CPC  = COMP;
    wire [SW-1:0] KC  = {SW{1'b0}} - NPOS;
    wire          apx = (ATYPE != 0) && (DYN == 0 || !ex);
    assign sum = {{(SW-W-LOGN){1'b0}}, T} + {{(SW-LOGN-1){1'b0}}, nneg} + KC + (apx ? CPC : {SW{1'b0}});
endmodule
