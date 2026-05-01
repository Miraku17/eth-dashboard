import type { ReactNode } from "react";

type Props = { children: ReactNode };

/**
 * Panel content wrapper that establishes a container-query context.
 * Inner Tailwind classes can use `@xs:`, `@sm:`, `@md:` etc. and they
 * trigger off this element's rendered width — independent of viewport.
 *
 * `w-full` is required because `@container` doesn't itself imply sizing;
 * without it the wrapper would shrink to its content and container-query
 * breakpoints would activate based on content width rather than allotted
 * column width.
 */
export default function PanelShell({ children }: Props) {
  return <div className="@container w-full">{children}</div>;
}
