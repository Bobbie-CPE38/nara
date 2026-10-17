import { DEMO_APPROVERS } from "@/lib/demo";

/**
 * Who the read-only pages look as (docs/workflow.md, sections 6.17 and 6.31). Not a real
 * login: the API shows each demo user only their own ward, and a Supervisor every ward.
 */
export function ActingAs({
  id,
  value,
  onChange,
}: {
  id: string;
  value: number;
  onChange: (staffId: number) => void;
}) {
  return (
    <label className="block text-sm" htmlFor={id}>
      Viewing as{" "}
      <select
        id={id}
        className="rounded border px-1"
        value={value}
        onChange={(event) => onChange(Number(event.target.value))}
      >
        {DEMO_APPROVERS.map((approver) => (
          <option key={approver.id} value={approver.id}>
            {approver.label}
          </option>
        ))}
      </select>
    </label>
  );
}
