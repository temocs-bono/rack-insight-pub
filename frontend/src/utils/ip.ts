/** Increment a dotted IPv4 address by `add`. Returns the input unchanged if it
 *  is not a valid IPv4 string, so generated values stay editable/fixable. */
export function incrementIpv4(ip: string, add: number): string {
  const parts = ip.trim().split(".");
  if (parts.length !== 4) return ip;
  const nums = parts.map((p) => Number(p));
  if (nums.some((n) => !Number.isInteger(n) || n < 0 || n > 255)) return ip;
  let value =
    nums[0] * 2 ** 24 + nums[1] * 2 ** 16 + nums[2] * 2 ** 8 + nums[3] + add;
  if (value < 0 || value > 0xffffffff) return ip;
  return [
    Math.floor(value / 2 ** 24) % 256,
    Math.floor(value / 2 ** 16) % 256,
    Math.floor(value / 2 ** 8) % 256,
    value % 256,
  ].join(".");
}
