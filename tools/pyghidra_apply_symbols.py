#!/usr/bin/env python3
"""Apply the static module's export table to an imported code_dec.bin.

Run after `analyzeHeadless ... -import code_dec.bin -processor ARM:LE:32:v7`:

    python3 tools/pyghidra_apply_symbols.py denpafree code_dec.bin \
            /root/modding/denpa_rev/data/symbols-base.csv

For every row it sets a primary label, and where the CSV address is odd - the
Thumb flag - it sets the TMode register context so Ghidra disassembles Thumb,
then creates a function there. Names stay mangled; Ghidra's demangler reads
them as Itanium C++ on demand.
"""
import csv, os, re, sys

os.environ.setdefault('GHIDRA_INSTALL_DIR', '/opt/ghidra')
PROJ_ROOT = '/root/ghidra-projects'


def main():
    proj, binname, csvpath = sys.argv[1:4]
    import pyghidra
    pyghidra.start()
    from ghidra.base.project import GhidraProject
    from ghidra.program.model.symbol import SourceType
    from ghidra.util.task import ConsoleTaskMonitor
    from java.math import BigInteger

    gp = GhidraProject.openProject(PROJ_ROOT, proj, False)
    prog = gp.openProgram('/', binname, False)
    tx = prog.startTransaction('apply lanai.crs exports')
    labelled = thumb = funcs = skipped = 0
    conflicts = []
    try:
        af = prog.getAddressFactory()
        mem, st = prog.getMemory(), prog.getSymbolTable()
        fm, ctx = prog.getFunctionManager(), prog.getProgramContext()
        tmode = ctx.getRegister('TMode')
        mon = ConsoleTaskMonitor()
        for row in csv.DictReader(open(csvpath)):
            if not row['address'] or row['segment'] != '.text':
                continue
            value = int(row['address'], 16)
            a = af.getAddress(hex(value & ~1))
            if not mem.contains(a):
                skipped += 1
                continue
            try:
                st.createLabel(a, row['name'], SourceType.IMPORTED)
                labelled += 1
            except Exception:
                skipped += 1
                continue
            if value & 1 and tmode is not None:
                try:
                    ctx.setValue(tmode, a, a, BigInteger.ONE)
                    thumb += 1
                except Exception:
                    # an instruction is already decoded here; Ghidra decided the
                    # mode during analysis and refuses to be overridden
                    conflicts.append(row['name'])
            if fm.getFunctionAt(a) is None:
                try:
                    fm.createFunction(row['name'], a,
                                      af.getAddressSet(a, a), SourceType.IMPORTED)
                    funcs += 1
                except Exception:
                    pass
    finally:
        prog.endTransaction(tx, True)
        gp.save(prog)
        print(f'labels {labelled}, thumb context {thumb}, '
              f'functions created {funcs}, skipped {skipped}, '
              f'thumb-context conflicts {len(conflicts)}')
        gp.close()


if __name__ == '__main__':
    main()
