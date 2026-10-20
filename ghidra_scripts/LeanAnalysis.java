import ghidra.app.script.GhidraScript;
public class LeanAnalysis extends GhidraScript {
    @Override public void run() throws Exception {
        String[] off = {"Decompiler Switch Analysis","Stack","Decompiler Parameter ID","Create Address Tables",
            "Embedded Media","ASCII Strings","Non-Returning Functions - Discovered","Scalar Operand References",
            "Data Reference","Function ID","Call Convention ID","Condense Filler Bytes","Subroutine References",
            "Shared Return Calls","Function Start Search","Function Start Search After Code","Function Start Search After Data",
            "Non-Returning Functions - Known","Variadic Function Signature Override","DWARF","Windows x86 PE RTTI Analyzer"};
        for (String o : off) {
            try { setAnalysisOption(currentProgram, o, "false"); println("disabled " + o); }
            catch (Exception e) { println("no such analyzer: " + o); }
        }
    }
}
