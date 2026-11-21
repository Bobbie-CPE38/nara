import type { ButtonHTMLAttributes } from "react";

/**
 * Classes of a button. The look of a plain button is in globals.css; the primary one is the
 * brand blue with white text (6.8:1) and is for the one action a section is about.
 */
const VARIANTS = {
  primary:
    "border-brand-600 bg-brand-600 text-white hover:border-brand-700 hover:bg-brand-700 disabled:hover:bg-brand-600",
  secondary: "",
} as const;

export function Button({
  variant = "secondary",
  className = "",
  type = "button",
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: keyof typeof VARIANTS }) {
  return <button type={type} className={`${VARIANTS[variant]} ${className}`} {...props} />;
}
