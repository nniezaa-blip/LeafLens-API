/**
Consumes one attempt for the key and reports whether it was allowed.
*/
export const isAttemptAllowed = async (limiter: RateLimit, key: string): Promise<boolean> => {
	const outcome = await limiter.limit({ key });
	return outcome.success;
};
