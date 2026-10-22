# Ghidra script: label code.bin with the names exported by app/lanai.crs.
#
# Run with analyzeHeadless, e.g.
#   /opt/ghidra/support/analyzeHeadless /root/ghidra-projects denpafree \
#       -import extracted/base/code_dec.bin -processor ARM:LE:32:v7 \
#       -loader BinaryLoader -loader-baseAddr 0x00100000 \
#       -postScript tools/ghidra_import_symbols.py data/symbols-base.csv
#
# Import code_dec.bin (the BLZ-decompressed .code) with image base 0x00100000,
# which is what the static module's segment table says .text is loaded at.
# An odd address in the CSV means the symbol is Thumb: the label goes on the
# even address and the register context is set so Ghidra disassembles Thumb.
# @category Denpa
import csv

from ghidra.program.model.symbol import SourceType

args = getScriptArgs()
path = args[0] if args else None
if not path:
    print('usage: ghidra_import_symbols.py <symbols.csv>')
else:
    space = currentProgram.getAddressFactory().getDefaultAddressSpace()
    tmode = currentProgram.getProgramContext().getRegister('TMode')
    named = thumb = skipped = 0
    with open(path) as fh:
        for row in csv.DictReader(fh):
            if not row['address']:
                continue
            value = int(row['address'], 16)
            addr = space.getAddress(value & ~1)
            if currentProgram.getMemory().contains(addr) is False:
                skipped += 1
                continue
            try:
                createLabel(addr, row['name'], True, SourceType.IMPORTED)
                named += 1
            except Exception as exc:
                skipped += 1
                continue
            if value & 1 and tmode is not None:
                try:
                    currentProgram.getProgramContext().setValue(
                        tmode, addr, addr, java.math.BigInteger.ONE)
                    thumb += 1
                except Exception:
                    pass
    print('labels created: %d (thumb context set on %d, skipped %d)'
          % (named, thumb, skipped))
