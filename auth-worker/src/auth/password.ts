import type Argon2 from '@phi-ag/argon2';

import { Argon2Type, Argon2Version } from '@phi-ag/argon2';

export interface PasswordCheck {
	encoded: string;
	password: string;
	pepper: string;
}

export interface PasswordParameters {
	memoryKib: number;
	pepper: string;
	timeCost: number;
}

const encoder = new TextEncoder();

/**
Mixes the server-side pepper into a password with HMAC-SHA256.
*/
const applyPepper = async (pepper: string, password: string): Promise<string> => {
	const key = await crypto.subtle.importKey(
		'raw',
		encoder.encode(pepper),
		{ hash: 'SHA-256', name: 'HMAC' },
		false,
		['sign'],
	);
	const signature = await crypto.subtle.sign('HMAC', key, encoder.encode(password));
	return btoa(String.fromCodePoint(...new Uint8Array(signature)));
};

/**
Hashes a password with argon2id and returns the encoded PHC string.
*/
export const hashPassword = async (
	argon2: Argon2,
	parameters: PasswordParameters,
	password: string,
): Promise<string> =>
	argon2.hash(await applyPepper(parameters.pepper, password), {
		hashLength: 32,
		memoryCost: parameters.memoryKib,
		parallelism: 1,
		timeCost: parameters.timeCost,
		type: Argon2Type.Argon2id,
		version: Argon2Version.Version13,
	}).encoded;

/**
Checks a password against an encoded argon2id hash.
*/
export const isPasswordCorrect = async (
	argon2: Argon2,
	{ encoded, password, pepper }: PasswordCheck,
): Promise<boolean> =>
	argon2.tryVerify(encoded, await applyPepper(pepper, password), Argon2Type.Argon2id).success;
