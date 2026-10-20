// Targeted export: args[0] = file with one Java regex per line (matched against function name),
// args[1] = output dir, args[2] = per-function decompile timeout seconds (default 300).
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;
import java.nio.file.Files;
import java.nio.file.Paths;
import java.util.ArrayList;
import java.util.List;
import java.util.regex.Pattern;

public class ExportList extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        List<Pattern> pats = new ArrayList<>();
        for (String line : Files.readAllLines(Paths.get(args[0]))) {
            line = line.trim();
            if (line.isEmpty() || line.startsWith("#")) continue;
            pats.add(Pattern.compile(line));
        }
        String outDir = args[1];
        int timeout = args.length > 2 ? Integer.parseInt(args[2]) : 300;
        new File(outDir).mkdirs();

        DecompInterface ifc = new DecompInterface();
        DecompileOptions dopt = new DecompileOptions(); dopt.setMaxPayloadMBytes(400); ifc.setOptions(dopt);
        ifc.openProgram(currentProgram);

        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        int n = 0;
        while (it.hasNext() && !monitor.isCancelled()) {
            Function f = it.next();
            String name = f.getName();
            boolean hit = false;
            for (Pattern p : pats) { if (p.matcher(name).find()) { hit = true; break; } }
            if (!hit) continue;
            String safe = name.replaceAll("[^A-Za-z0-9_@.]", "_");
            if (safe.length() > 200) safe = safe.substring(0, 200);
            File outFile = new File(outDir, safe + ".c");
            if (outFile.exists() && outFile.length() > 0) continue;
            long t0 = System.currentTimeMillis();
            String c;
            try {
                DecompileResults res = ifc.decompileFunction(f, timeout, monitor);
                c = res.decompileCompleted() ? res.getDecompiledFunction().getC()
                                             : "// decompile failed: " + res.getErrorMessage();
            } catch (Exception e) {
                c = "// decompile exception: " + e;
            }
            try (PrintWriter pw = new PrintWriter(new FileWriter(outFile))) { pw.print(c); }
            n++;
            println("exported " + name + " (" + f.getBody().getNumAddresses() + " bytes, "
                    + (System.currentTimeMillis() - t0) / 1000 + "s)");
        }
        ifc.dispose();
        println("done exported=" + n);
    }
}
