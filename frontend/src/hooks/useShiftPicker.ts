"use client";

import { useCallback, useState } from "react";
import { useBackendClock } from "@/components/ClockProvider";
import { usePolling } from "@/hooks/usePolling";
import { apiRequest } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import type { DemoRosterPerson, DemoShift, DemoWard } from "@/lib/types/demo";

const stopAfterFirstRead = () => true;

/**
 * The Demo control's choice of a ward, a day, a shift and a person on it, from the database
 * rather than a copy of the seed (round 6 PR EV6, docs/workflow.md 6.36.5): any ward, any day,
 * anyone on the roster. The day starts at the day of the Backend Clock.
 */
export function useShiftPicker() {
  const loadWards = useCallback(
    (signal: AbortSignal) => apiRequest<DemoWard[]>("/demo/wards", { signal }),
    [],
  );
  const wardsRead = usePolling(loadWards, { stopOnData: stopAfterFirstRead });
  // A Float Pool has no shifts of its own (6.19). Anything but a list reads as no wards
  const wards = (Array.isArray(wardsRead.data) ? wardsRead.data : []).filter((ward) => !ward.is_float_pool);

  const clockNow = useBackendClock().data?.now;
  const [wardChoice, setWardChoice] = useState<number | null>(null);
  const [dateChoice, setDateChoice] = useState<string | null>(null);
  const [shiftChoice, setShiftChoice] = useState<number | null>(null);
  const [staffChoice, setStaffChoice] = useState<number | null>(null);

  const ward = wards.find((item) => item.id === wardChoice) ?? wards[0];
  const date = dateChoice ?? (clockNow ? formatDateTime(clockNow).slice(0, 10) : "");
  const loadShifts = useCallback(
    (signal: AbortSignal) =>
      apiRequest<DemoShift[]>(`/demo/shifts?ward_id=${ward?.id}&date=${encodeURIComponent(date)}`, {
        signal,
      }),
    [ward?.id, date],
  );
  const shiftsRead = usePolling(loadShifts, { enabled: ward !== undefined && date !== "" });
  const shifts = Array.isArray(shiftsRead.data) ? shiftsRead.data : [];
  const shift = shifts.find((item) => item.id === shiftChoice) ?? shifts[0];
  const people: DemoRosterPerson[] = shift?.people ?? [];
  const person = people.find((item) => item.staff_id === staffChoice) ?? people[0];

  return {
    wards,
    ward,
    date,
    shifts,
    shift,
    people,
    person,
    error: wardsRead.error ?? shiftsRead.error,
    pickWard(id: number) {
      setWardChoice(id);
      setShiftChoice(null);
      setStaffChoice(null);
    },
    pickDate(value: string) {
      setDateChoice(value);
      setShiftChoice(null);
      setStaffChoice(null);
    },
    pickShift(id: number) {
      setShiftChoice(id);
      setStaffChoice(null);
    },
    pickPerson: setStaffChoice,
    /** Read the shifts again, after a check-in or a leave changed them */
    refresh: shiftsRead.refresh,
    /**
     * Read the wards and the shifts again, after a reset or a test run changed them (review of
     * #145): the ward list is read once, and a reset no longer reloads the page. A picked ward,
     * shift or person that is gone falls back to the first one
     */
    reload: () => Promise.all([wardsRead.refresh(), shiftsRead.refresh()]),
  };
}
