"use client";

import type { ReactNode } from "react";

type Column<T> = {
  key: string;
  header: string;
  align?: "left" | "right";
  className?: string;
  render: (row: T) => ReactNode;
};

type Props<T> = {
  columns: readonly Column<T>[];
  rows: readonly T[];
  getRowKey: (row: T, index: number) => string;
  emptyMessage: string;
  caption?: string;
};

export function Table<T>({ columns, rows, getRowKey, emptyMessage, caption }: Props<T>) {
  if (rows.length === 0) {
    return <div className="table-empty">{emptyMessage}</div>;
  }

  return (
    <div className="table-scroll" tabIndex={0} aria-label={caption ?? "Scrollable data table"}>
      <table className="data-table">
        {caption ? <caption className="sr-only">{caption}</caption> : null}
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.key}
                className={column.className}
                data-align={column.align ?? "left"}
                scope="col"
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, index) => (
            <tr key={getRowKey(row, index)}>
              {columns.map((column) => (
                <td
                  key={column.key}
                  className={column.className}
                  data-align={column.align ?? "left"}
                >
                  {column.render(row)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export type { Column as TableColumn };
