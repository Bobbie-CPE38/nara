import type { MessageKey } from "@/lib/i18n";

// Helpers of the login pages. They live here, not in the page files: a Next.js page may export
// only its component.

export const PASSWORD_MIN_LENGTH = 12;
export const PASSWORD_MAX_LENGTH = 128;

/** A staff ID is a whole number; anything else is told so before the Backend is asked. */
export function parseStaffId(text: string): number | null {
  const value = text.trim();
  if (!/^\d+$/.test(value)) return null;
  const id = Number(value);
  return Number.isSafeInteger(id) && id > 0 ? id : null;
}

/** The reason a new password is refused before the Backend is asked, or null. Counts characters, not bytes. */
export function passwordProblem(password: string, repeat: string): MessageKey | null {
  const length = [...password].length;
  if (length < PASSWORD_MIN_LENGTH || length > PASSWORD_MAX_LENGTH) return "auth.password.tooShort";
  if (password !== repeat) return "auth.password.mismatch";
  return null;
}

/** A time typed in the page (Bangkok, as the rest of the web app shows it) as the aware time the API wants. */
export function bangkokIso(local: string): string | undefined {
  const value = local.trim();
  if (value === "") return undefined;
  return value.length === 16 ? `${value}:00+07:00` : `${value}+07:00`;
}
