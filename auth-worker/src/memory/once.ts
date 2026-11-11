/**
Wraps a function so it runs on the first call and later calls share that result.
*/
export const once = <Result>(compute: () => Result): (() => Result) => {
	let state: undefined | { value: Result };
	return () => {
		state ??= { value: compute() };
		return state.value;
	};
};
