import { writeFile } from "node:fs/promises";
import { join } from "node:path";

export async function writeInvocationRecord(directory, mode, sequence, kind, content) {
  if (!["run", "approve"].includes(mode) || !Number.isSafeInteger(sequence) || sequence < 1 ||
      !["success", "failure"].includes(kind)) throw new Error("Invalid invocation record identity");
  await writeFile(join(directory, `${mode}-${sequence}-${kind}.json`), content,
    { flag: "wx", mode: 0o600 });
}

export function failureRecord(error, args) {
  return JSON.stringify({
    args,
    code: Number.isInteger(error?.code) || /^[A-Z_]{1,40}$/.test(error?.code ?? "") ? error.code : null,
    signal: /^SIG[A-Z0-9]{1,16}$/.test(error?.signal ?? "") ? error.signal : null,
    killed: error?.killed === true,
    stdout: typeof error?.stdout === "string" ? error.stdout : "",
    stderr: typeof error?.stderr === "string" ? error.stderr : "",
  });
}
