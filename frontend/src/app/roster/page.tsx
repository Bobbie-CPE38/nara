"use client";

import Link from "next/link";
import { useCallback, useState } from "react";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import { formatDemoTime } from "@/lib/demo";
import type { ShiftRoster } from "@/lib/types/roster";

function Roster({ shiftId }: { shiftId: number }) {
  const load = useCallback((signal: AbortSignal) => apiRequest<ShiftRoster>(`/roster?shift_id=${shiftId}`, {
    demoUser: 900, signal,
  }), [shiftId]);
  const { data, error, isLoading } = usePolling(load);
  return <section className="mt-6 space-y-4" aria-label="Shift roster">
    {isLoading && <p role="status">Loading roster…</p>}
    {error && <p role="alert" className="text-red-700">Could not refresh roster: {error.message}</p>}
    {data && <>
      <h2 className="text-lg font-semibold">{data.shift.ward_name} · Shift {data.shift.id} · {data.shift.shift_type}{!data.shift.is_active && " · Inactive"}</h2>
      <p>{formatDemoTime(data.shift.start_at)} – {formatDemoTime(data.shift.end_at)} (Bangkok)</p>
      {data.assignments.length === 0 ? <p>No assignments for this shift.</p> : <div className="overflow-x-auto rounded border border-slate-300">
        <table className="w-full text-left text-sm">
          <caption className="sr-only">All assignments for shift {shiftId}</caption>
          <thead className="bg-slate-100"><tr>{["Assignment", "Staff", "Role", "Home ward", "Staff status", "Roster status", "Assignment type", "Source"].map(label => <th key={label} scope="col" className="p-3">{label}</th>)}</tr></thead>
          <tbody>{data.assignments.map(row => <tr key={row.id} className="border-t border-slate-200">
            <td className="p-3">{row.id}</td><td className="p-3">{row.staff_id} — {row.first_name} {row.last_name}</td>
            <td className="p-3">{row.role_name}</td><td className="p-3">{row.home_ward_name}{row.home_ward_id !== data.shift.ward_id && " (cross-ward)"}</td>
            <td className="p-3">{row.staff_status}</td><td className="p-3 font-medium">{row.status}</td>
            <td className="p-3">{row.assignment_type}</td><td className="p-3">{row.candidate_source ?? "—"}</td>
          </tr>)}</tbody>
        </table>
      </div>}
      <p className="text-sm text-slate-600">Shows every assignment, including cancelled rows. Multiple rows may belong to the same staff member.</p>
    </>}
  </section>;
}

export default function RosterPage() {
  const [shiftId, setShiftId] = useState(1);
  return <main className="mx-auto max-w-7xl p-6 text-slate-900">
    <nav className="mb-6 flex gap-4"><Link href="/" className="text-blue-700 underline">Home</Link><Link href="/demo/line-sim" className="text-blue-700 underline">LINE simulator</Link></nav>
    <h1 className="text-2xl font-semibold">Shift roster</h1>
    <p className="mt-2 text-slate-600">View the demo roster as staff 900. Updates every 2 seconds.</p>
    <label className="mt-6 block" htmlFor="shift">Shift</label>
    <select id="shift" className="mt-2 rounded border border-slate-400 p-2" value={shiftId} onChange={event => setShiftId(Number(event.target.value))}>
      <option value={1}>1 — ICU night shift</option><option value={2}>2 — ICU day shift</option>
    </select>
    <Roster key={shiftId} shiftId={shiftId} />
  </main>;
}
