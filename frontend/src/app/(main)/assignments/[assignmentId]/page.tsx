"use client";

import { useParams } from "next/navigation";
import { AssignmentView } from "@/components/assignment/assignment-view";
import { RequireAuth } from "@/lib/auth/require-auth";

export default function AssignmentPage() {
  const { assignmentId } = useParams<{ assignmentId: string }>();
  return (
    <RequireAuth>
      <AssignmentView key={assignmentId} id={assignmentId} />
    </RequireAuth>
  );
}
