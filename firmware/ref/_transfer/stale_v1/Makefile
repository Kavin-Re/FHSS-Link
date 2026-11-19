# FHSS-Link firmware reference, host build. C99, no dynamic allocation in src/. NOT run on any ESP32.
CC      ?= gcc
CSTD    := -std=c99 -Wall -Wextra -Wpedantic -Wshadow -Wconversion -Werror
OPT     ?= -O2 -g
SRC     := $(wildcard src/*.c)
INC     := -Iinclude -Isrc -Isim
BUILD   := build
SAN     := -fsanitize=address,undefined -fno-sanitize-recover=all -fno-omit-frame-pointer
# vectors: the existing hop_engine vectors (read-only). Override if the repo layout differs.
VEC     ?= ../../rtl/hop_engine/vectors
SIMREF  ?= ../../sim
PY      ?= python3
ITERS   ?= 2000000
all: $(BUILD)/test_main
$(BUILD):
	mkdir -p $(BUILD)
$(BUILD)/test_main: $(SRC) tests/test_main.c tests/test_state.c | $(BUILD)
	$(CC) $(CSTD) $(OPT) $(INC) $^ -o $@
test: $(BUILD)/test_main
	$(BUILD)/test_main $(VEC)
clean:
	rm -rf $(BUILD)
.PHONY: all test clean
