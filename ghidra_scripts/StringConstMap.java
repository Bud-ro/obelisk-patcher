// Build a map of static YYRValue string constants: find every caller of YYCreateString /
// YYSetString, decompile it, and extract (slot address, literal) pairs. args[0] = output file.
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.address.Address;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import ghidra.program.model.symbol.Reference;
import ghidra.program.model.symbol.ReferenceIterator;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.util.LinkedHashSet;
import java.util.Set;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class StringConstMap extends GhidraScript {
    @Override
    public void run() throws Exception {
        String out = getScriptArgs()[0];
        Set<Function> targets = new LinkedHashSet<>();
        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        while (it.hasNext()) {
            Function f = it.next();
            String n = f.getName();
            if (n.startsWith("YYCreateString") || n.startsWith("YYSetString")) targets.add(f);
        }
        println("string ctor functions: " + targets.size());
        Set<Function> callers = new LinkedHashSet<>();
        for (Function t : targets) {
            ReferenceIterator ri = currentProgram.getReferenceManager().getReferencesTo(t.getEntryPoint());
            while (ri.hasNext()) {
                Reference r = ri.next();
                Function c = getFunctionContaining(r.getFromAddress());
                if (c != null) callers.add(c);
            }
        }
        println("callers: " + callers.size());
        DecompInterface ifc = new DecompInterface();
        ifc.setOptions(new DecompileOptions());
        ifc.openProgram(currentProgram);
        Pattern pat = Pattern.compile(
            "(?:YYCreateString|YYSetString)\\s*\\(\\s*\\(RValue \\*\\)\\s*&?([A-Za-z0-9_]+)\\s*,\\s*(.*?)\\)\\s*;");
        int pairs = 0, done = 0;
        try (PrintWriter pw = new PrintWriter(new FileWriter(out))) {
            for (Function c : callers) {
                if (monitor.isCancelled()) break;
                DecompileResults res = ifc.decompileFunction(c, 300, monitor);
                done++;
                if (!res.decompileCompleted()) { pw.println("# FAILED " + c.getName()); continue; }
                String src = res.getDecompiledFunction().getC();
                Matcher m = pat.matcher(src);
                while (m.find()) {
                    pw.println(m.group(1) + "\t" + m.group(2).replace("\n", " ") + "\t" + c.getName());
                    pairs++;
                }
                if (done % 50 == 0) { println("decompiled " + done + "/" + callers.size() + " pairs=" + pairs); pw.flush(); }
            }
        }
        ifc.dispose();
        println("done callers=" + done + " pairs=" + pairs);
    }
}
