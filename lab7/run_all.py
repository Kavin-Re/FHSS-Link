"""Run every lab7 script, then the assertion suite. Simulation only. Usage: python3 run_all.py"""
import subprocess, sys, os
h = os.path.dirname(os.path.abspath(__file__))
for s in "b05_timing b06_carryoff b12_fuzz b13_dolevyao b15_permleak b16_traffic b20_fish b23_redblue".split():
    subprocess.run([sys.executable, os.path.join(h, s + ".py")], check=True)
subprocess.run([sys.executable, os.path.join(h, "test_lab7.py")], check=True)
