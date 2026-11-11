import type Argon2 from '@phi-ag/argon2';

import type { PasswordParameters } from './password.ts';

import { hashPassword } from './password.ts';

const cache: { hash?: Promise<string> } = {};

/**
Returns a throwaway hash so unknown emails cost the same as real ones.
*/
export const getDummyHash = async (
	argon2: Argon2,
	parameters: PasswordParameters,
): Promise<string> => {
	cache.hash ??= hashPassword(argon2, parameters, crypto.randomUUID());
	return cache.hash;
};
