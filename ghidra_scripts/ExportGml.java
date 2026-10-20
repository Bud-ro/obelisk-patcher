// Headless Ghidra post-script: decompile every function whose name contains "gml_"
// and write one .c file per function plus an index.txt (entry, size, name).
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.DecompInterface;
import ghidra.app.decompiler.DecompileOptions;
import ghidra.app.decompiler.DecompileResults;
import ghidra.program.model.listing.Function;
import ghidra.program.model.listing.FunctionIterator;
import java.io.File;
import java.io.FileWriter;
import java.io.PrintWriter;

public class ExportGml extends GhidraScript {
    @Override
    public void run() throws Exception {
        String[] args = getScriptArgs();
        String outDir = args.length > 0 ? args[0] : "/tmp/ghidra_out";
        new File(outDir).mkdirs();

        DecompInterface ifc = new DecompInterface();
        ifc.setOptions(new DecompileOptions());
        ifc.openProgram(currentProgram);

        FunctionIterator it = currentProgram.getFunctionManager().getFunctions(true);
        int n = 0, failed = 0;
        try (PrintWriter idx = new PrintWriter(new FileWriter(new File(outDir, "index.txt")))) {
            while (it.hasNext() && !monitor.isCancelled()) {
                Function f = it.next();
                String name = f.getName();
                if (!name.contains("gml_")) continue;
                String c;
                try {
                    DecompileResults res = ifc.decompileFunction(f, 180, monitor);
                    if (res.decompileCompleted()) {
                        c = res.getDecompiledFunction().getC();
                    } else {
                        c = "// decompile failed: " + res.getErrorMessage();
                        failed++;
                    }
                } catch (Exception e) {
                    c = "// decompile exception: " + e;
                    failed++;
                }
                String safe = name.replaceAll("[^A-Za-z0-9_@.]", "_");
                if (safe.length() > 200) safe = safe.substring(0, 200);
                try (PrintWriter pw = new PrintWriter(new FileWriter(new File(outDir, safe + ".c")))) {
                    pw.print(c);
                }
                idx.println(f.getEntryPoint() + " " + f.getBody().getNumAddresses() + " " + name);
                n++;
                if (n % 100 == 0) {
                    println("exported " + n);
                    idx.flush();
                }
            }
        }
        ifc.dispose();
        println("done exported=" + n + " failed=" + failed);
    }
}
