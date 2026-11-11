import { generateKeyPairSync, randomBytes } from 'node:crypto';
import { existsSync, writeFileSync } from 'node:fs';

const DEV_VARS_PATH = '.dev.vars';
const force = process.argv.includes('--force');

if (existsSync(DEV_VARS_PATH) && !force) {
	throw new Error(`${DEV_VARS_PATH} exists; pass --force to replace it`);
}

const { privateKey } = generateKeyPairSync('rsa', { modulusLength: 2048 });
const kid = randomBytes(8).toString('base64url');
const exported = privateKey.export({ format: 'jwk' }) as Record<string, string>;

const privateJwk = { ...exported, alg: 'RS256', kid, kty: 'RSA' };
const publicJwk = { alg: 'RS256', e: exported['e'], kid, kty: 'RSA', n: exported['n'] };

const pepper = randomBytes(48).toString('base64');

const lines = [
	`JWT_PRIVATE_JWK='${JSON.stringify(privateJwk)}'`,
	`JWT_PUBLIC_JWKS='${JSON.stringify([publicJwk])}'`,
	`PASSWORD_PEPPER='${pepper}'`,
];

writeFileSync(DEV_VARS_PATH, `${lines.join('\n')}\n`, { mode: 0o600 });
console.log(`wrote ${DEV_VARS_PATH} (kid ${kid})`);
