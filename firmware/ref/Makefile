# FHSS-Link firmware reference, host build. C99, no dynamic allocation in src/. NOT run on any ESP32.
CC      ?= gcc
CSTD    := -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
OPT     ?= -O2 -g
SRC     := $(wildcard src/*.c)
INC     := -Iinclude -Isrc -Isim -Ihal
BUILD   := build
SAN     := -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer
# vectors: the existing hop_engine vectors (read-only). Override if the repo layout differs.
VEC     ?= ../../rtl/hop_engine/vectors
SIMREF  ?= ../../sim
PY      ?= python3
ITERS   ?= 2000000
all: $(BUILD)/test_main $(BUILD)/xval $(BUILD)/demo_host $(BUILD)/demo_safe
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/test_main: $(SRC) tests/test_main.c tests/test_state.c | $(BUILD)
	$(CC) $(CSTD) $(OPT) $(INC) $^ -o $@
test: $(BUILD)/test_main $(BUILD)/xval
	$(BUILD)/test_main $(VEC)
	$(PY) tests/xval.py $(BUILD)/xval $(REPO)
DEMOSRC := $(SRC) sim/mock_radio.c sim/demo.c
$(BUILD)/demo_host: $(DEMOSRC) | $(BUILD)
	$(CC) $(CSTD) $(OPT) -DFH_SIM_UNSAFE_LIMITS $(INC) $^ -o $@
$(BUILD)/demo_safe: $(DEMOSRC) | $(BUILD)
	$(CC) $(CSTD) $(OPT) $(INC) $^ -o $@
$(BUILD)/xval: $(SRC) tests/xval.c | $(BUILD)
	$(CC) $(CSTD) $(OPT) $(INC) $^ -o $@
REPO ?= ../..
xval: $(BUILD)/xval
	$(PY) tests/xval.py $(BUILD)/xval $(REPO)
$(BUILD)/fuzz_main: $(SRC) fuzz/fuzz_main.c | $(BUILD)
	$(CC) $(CSTD) $(OPT) $(INC) $^ -o $@
$(BUILD)/test_san: $(SRC) tests/test_main.c tests/test_state.c | $(BUILD)
	$(CC) $(CSTD) -O1 -g -Wno-sign-conversion $(SAN) $(INC) $^ -o $@
$(BUILD)/fuzz_san: $(SRC) fuzz/fuzz_main.c | $(BUILD)
	$(CC) $(CSTD) -O1 -g -Wno-sign-conversion $(SAN) $(INC) $^ -o $@
$(BUILD)/demo_san: $(DEMOSRC) | $(BUILD)
	$(CC) $(CSTD) -O1 -g -Wno-sign-conversion $(SAN) -DFH_SIM_UNSAFE_LIMITS $(INC) $^ -o $@
fuzz: $(BUILD)/fuzz_main
	$(BUILD)/fuzz_main $(ITERS) 1
# sanitizer run (cloud): unit tests + vectors, fuzz (2 seeds), full demo
san: $(BUILD)/test_san $(BUILD)/fuzz_san $(BUILD)/demo_san
	$(BUILD)/test_san $(VEC)
	$(BUILD)/fuzz_san $(ITERS) 1
	$(BUILD)/fuzz_san $(ITERS) 2
	$(BUILD)/demo_san --scenario phases --slots 3000 --out $(BUILD)/san_phases
# the library objects must not reference any allocator
nomalloc: $(SRC) | $(BUILD)
	@for f in $(SRC); do $(CC) $(CSTD) -O2 $(INC) -c $$f -o $(BUILD)/chk.o && ! nm -u $(BUILD)/chk.o | grep -E ' (malloc|calloc|realloc|free)$$' ; done && echo "nomalloc: OK (no allocator symbols in src/*.o)"
# demo logs (the dashboard replays *.log: Source = Replay)
logs: $(BUILD)/demo_host $(BUILD)/demo_safe
	mkdir -p logs
	$(BUILD)/demo_host --scenario clean --slots 3000 --out logs/fw_clean
	$(BUILD)/demo_host --scenario phases --slots 3000 --out logs/fw_phases
	$(BUILD)/demo_host --scenario sweep --slots 3000 --out logs/fw_sweep
	$(BUILD)/demo_host --scenario static --slots 3000 --out logs/fw_static
	$(BUILD)/demo_safe --scenario static --slots 3000 --out logs/fw_static_guarded
clean:
	rm -rf $(BUILD)
.PHONY: all test clean xval fuzz san nomalloc logs
