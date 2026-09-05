import assert from "node:assert/strict";
import { execFileSync } from "node:child_process";
import { createDecipheriv, randomBytes } from "node:crypto";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";

test("encrypted evidence round-trips, rejects tampering, and never overwrites", async () => {
  const directory = await mkdtemp(join(tmpdir(), "flow-pilot-encryption-test-"));
  try {
    const input = join(directory, "input");
    const output = join(directory, "sealed");
    const key = randomBytes(32);
    const secret = "private evidence must not appear in the artifact";
    await writeFile(input, secret);
    const args = [fileURLToPath(new URL("seal-pilot-evidence.mjs", import.meta.url)), input, output];
    const options = { env: { PATH: process.env.PATH, FLOW_PILOT_EVIDENCE_KEY: key.toString("hex") }, stdio: "pipe" };
    execFileSync(process.execPath, args, options);
    const sealed = await readFile(output);
    assert.equal(sealed.includes(Buffer.from(secret)), false);
    assert.equal(sealed.subarray(0, 9).toString(), "FLOW106V1");
    function decrypt(bytes) {
      const decipher = createDecipheriv("aes-256-gcm", key, bytes.subarray(9, 21));
      decipher.setAAD(Buffer.from("flow-pilot-106-v1"));
      decipher.setAuthTag(bytes.subarray(-16));
      return Buffer.concat([decipher.update(bytes.subarray(21, -16)), decipher.final()]).toString();
    }
    assert.equal(decrypt(sealed), secret);
    const tampered = Buffer.from(sealed);
    tampered[21] ^= 1;
    assert.throws(() => decrypt(tampered));
    assert.throws(() => execFileSync(process.execPath, args, options));
    assert.deepEqual(await readFile(output), sealed);
    assert.throws(() => execFileSync(process.execPath, [args[0], input, output + ".missing-key"],
      { env: { PATH: process.env.PATH }, stdio: "pipe" }));
  } finally {
    await rm(directory, { recursive: true, force: true });
  }
});
