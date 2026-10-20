import ghidra.app.script.GhidraScript;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.util.TreeMap;
public class RefsTo extends GhidraScript {
    @Override public void run() throws Exception {
        for (String a : getScriptArgs()) {
            String[] parts = a.split("=");
            long base = Long.parseLong(parts[1].replace("0x",""), 16);
            TreeMap<String,Integer> m = new TreeMap<>();
            for (long off : new long[]{0, 8}) {
                Address addr = toAddr(base + off);
                ReferenceIterator ri = currentProgram.getReferenceManager().getReferencesTo(addr);
                while (ri.hasNext()) {
                    Reference r = ri.next();
                    Function f = getFunctionContaining(r.getFromAddress());
                    String k = f == null ? "?" : f.getName();
                    m.merge(k, 1, Integer::sum);
                }
            }
            StringBuilder sb = new StringBuilder("== " + parts[0] + " (" + m.size() + " funcs): ");
            for (var e : m.entrySet()) sb.append(e.getKey()).append("x").append(e.getValue()).append("  ");
            println(sb.toString());
        }
    }
}
