"use client";

import { useState } from "react";

import type { Transaction } from "@/lib/types";

import { TransactionDetails } from "./transaction-details";
import { TransactionForm, type TransactionFormDefaults } from "./transaction-form";

type FormTarget = { transaction?: Transaction };

/**
 * State and elements for the details drawer (T-2) and the create/edit dialog (T-3),
 * shared by the full screen and the embeddable list.
 */
export function useTransactionOverlays({
  initialDetailsId = null,
  initialFormOpen = false,
  defaults,
  onDetailsClosed,
  onFormClosed,
}: {
  initialDetailsId?: number | null;
  initialFormOpen?: boolean;
  defaults?: TransactionFormDefaults;
  onDetailsClosed?: () => void;
  onFormClosed?: () => void;
} = {}) {
  const [detailsId, setDetailsId] = useState<number | null>(initialDetailsId);
  const [form, setForm] = useState<FormTarget | null>(initialFormOpen ? {} : null);

  const closeDetails = () => {
    setDetailsId(null);
    onDetailsClosed?.();
  };
  const closeForm = () => {
    setForm(null);
    onFormClosed?.();
  };

  const element = (
    <>
      {detailsId !== null && (
        <TransactionDetails
          id={detailsId}
          onClose={closeDetails}
          onDeleted={closeDetails}
          onEdit={(transaction) => {
            closeDetails();
            setForm({ transaction });
          }}
        />
      )}
      {form && (
        <TransactionForm
          // Remount for another target so the form starts from fresh values.
          key={form.transaction?.id ?? "new"}
          transaction={form.transaction}
          defaults={defaults}
          onClose={closeForm}
          onSaved={closeForm}
        />
      )}
    </>
  );

  return {
    openDetails: (id: number) => setDetailsId(id),
    openCreate: () => setForm({}),
    element,
  };
}
