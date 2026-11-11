import { z } from 'zod';

const EMAIL_PATTERN = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

/**
Credentials accepted by register and login.
*/
export const credentialsSchema = z.object({
	email: z
		.string()
		.trim()
		.toLowerCase()
		.max(320)
		.refine((value) => EMAIL_PATTERN.test(value), 'invalid email address'),
	password: z.string().min(8).max(200),
});

export type Credentials = z.infer<typeof credentialsSchema>;
