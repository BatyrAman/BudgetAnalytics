import { describe, expect, it } from "vitest";

import { ApiError, errorFromResponse, networkError, toUserMessage } from "./errors";

function response(status: number, body: unknown, headers: Record<string, string> = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json", ...headers },
  });
}

describe("errorFromResponse", () => {
  it("reads the machine code and request id, never the English detail", async () => {
    const error = await errorFromResponse(
      response(400, {
        detail: "Category 'Зарплата' (income) cannot be used for a expense transaction",
        code: "category_kind_mismatch",
        request_id: "req-1",
      }),
    );
    expect(error).toMatchObject({
      status: 400,
      code: "category_kind_mismatch",
      requestId: "req-1",
    });
    expect(toUserMessage(error)).toBe("Категория не подходит для этого типа операции.");
    expect(toUserMessage(error)).not.toContain("cannot");
  });

  it("maps Pydantic 422 issues to Russian field errors by type", async () => {
    const error = await errorFromResponse(
      response(422, {
        detail: [
          { loc: ["body", "amount"], msg: "Input should be greater than 0", type: "greater_than" },
          { loc: ["body", "category_id"], msg: "Field required", type: "missing" },
        ],
        code: "validation_error",
      }),
    );
    expect(error.fieldErrors).toEqual([
      { field: "amount", message: "Значение должно быть больше нуля.", type: "greater_than" },
      { field: "category_id", message: "Обязательное поле.", type: "missing" },
    ]);
  });

  it("uses Retry-After for 429 and marks it retryable", async () => {
    const error = await errorFromResponse(
      response(
        429,
        { detail: "Too Many Requests", code: "too_many_requests" },
        { "Retry-After": "42" },
      ),
    );
    expect(error.retryAfterSeconds).toBe(42);
    expect(error.retryable).toBe(true);
    expect(toUserMessage(error)).toBe("Слишком много запросов. Повторите через 42 с.");
  });

  it("survives a non-JSON body and falls back to the status", async () => {
    const error = await errorFromResponse(
      new Response("<html>bad gateway</html>", { status: 502 }),
    );
    expect(error.code).toBe("http_502");
    expect(toUserMessage(error)).toBe("Ошибка на сервере. Попробуйте позже.");
    expect(toUserMessage(error)).not.toContain("html");
  });
});

describe("toUserMessage", () => {
  it.each([
    [401, "unauthorized", "Сессия истекла. Войдите снова."],
    [403, "forbidden", "Недостаточно прав для этого действия."],
    [404, "not_found", "Не найдено. Возможно, запись была удалена."],
    [409, "conflict", "Действие конфликтует с текущими данными."],
    [500, "internal_error", "Ошибка на сервере. Попробуйте позже."],
  ])("status %i without a specific code", (status, code, message) => {
    expect(toUserMessage(new ApiError({ status, code }))).toBe(message);
  });

  it("lets a screen override the text for a code", () => {
    const error = new ApiError({ status: 409, code: "category_in_use" });
    expect(
      toUserMessage(error, { category_in_use: "Сначала уберите категорию из операций." }),
    ).toBe("Сначала уберите категорию из операций.");
  });

  it("handles network failures and unknown values", () => {
    expect(toUserMessage(networkError())).toBe(
      "Нет связи с сервером. Проверьте подключение и повторите.",
    );
    expect(networkError().retryable).toBe(true);
    expect(toUserMessage(new Error("boom"))).toBe("Ошибка на сервере. Попробуйте позже.");
    expect(new ApiError({ status: 400, code: "bad_request" }).retryable).toBe(false);
  });
});
