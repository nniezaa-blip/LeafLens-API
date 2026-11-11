import Argon2 from '@phi-ag/argon2';
import wasm from '@phi-ag/argon2/argon2.wasm';

import { once } from '../memory/once.ts';

/**
Returns the isolate's argon2 instance, compiling the WASM on first use.
*/
export const getArgon2: () => Promise<Argon2> = once(
	async () => new Argon2(await WebAssembly.instantiate(wasm)),
);
