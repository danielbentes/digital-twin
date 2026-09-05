import { createCipheriv, randomBytes } from "node:crypto";
import { createReadStream, createWriteStream } from "node:fs";
import { appendFile } from "node:fs/promises";
import { pipeline } from "node:stream/promises";

const key = process.env.FLOW_PILOT_EVIDENCE_KEY;
if (!/^[a-f0-9]{64}$/.test(key ?? "")) throw new Error("Evidence encryption key unavailable");
const nonce = randomBytes(12);
const cipher = createCipheriv("aes-256-gcm", Buffer.from(key, "hex"), nonce);
cipher.setAAD(Buffer.from("flow-pilot-106-v1"));
const output = createWriteStream(process.argv[3], { flags: "wx", mode: 0o600 });
output.write(Buffer.concat([Buffer.from("FLOW106V1"), nonce]));
await pipeline(createReadStream(process.argv[2]), cipher, output);
await appendFile(process.argv[3], cipher.getAuthTag());
