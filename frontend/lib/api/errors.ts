/**
 * Unified API error layer (G-10).
 *
 * Every failed request becomes an `ApiError`. User-facing text is chosen by the
 * machine `code` returned by the backend (never by parsing the English `detail`),
 * falling back to the HTTP status. Internal details are never shown to users.
 */

/** `type` is the stable Pydantic issue type, for screens that refine `message`. */
export type FieldError = { field: string; message: string; type?: string };

type ValidationIssue = { loc?: (string | number)[]; msg?: string; type?: string };

type ErrorBody = {
  detail?: string | ValidationIssue[];
  code?: string;
  request_id?: string | null;
};

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly requestId: string | null;
  readonly fieldErrors: FieldError[];
  readonly retryAfterSeconds: number | null;

  constructor(init: {
    status: number;
    code: string;
    requestId?: string | null;
    fieldErrors?: FieldError[];
    retryAfterSeconds?: number | null;
  }) {
    super(`API error ${init.status} (${init.code})`);
    this.name = "ApiError";
    this.status = init.status;
    this.code = init.code;
    this.requestId = init.requestId ?? null;
    this.fieldErrors = init.fieldErrors ?? [];
    this.retryAfterSeconds = init.retryAfterSeconds ?? null;
  }

  /** True for failures that may succeed if the same request is repeated. */
  get retryable(): boolean {
    return this.status === 0 || this.status === 429 || this.status >= 500;
  }
}

/** Russian messages for backend business error codes (see docs/design/API_TO_UI_MAPPING.md). */
const CODE_MESSAGES: Record<string, string> = {
  // auth
  invalid_credentials: "Неверный e-mail или пароль.",
  inactive_user: "Аккаунт деактивирован.",
  email_taken: "Этот e-mail уже зарегистрирован.",
  wrong_password: "Неверный текущий пароль.",
  invalid_token: "Сессия недействительна. Войдите снова.",
  token_expired: "Сессия истекла. Войдите снова.",
  // categories
  category_not_found: "Категория не найдена или недоступна.",
  category_kind_mismatch: "Категория не подходит для этого типа операции.",
  system_category_readonly: "Системные категории нельзя изменить.",
  category_exists: "Категория с таким названием уже есть.",
  category_in_use: "Категория используется в операциях или бюджетах — удалить нельзя.",
  category_kind_conflict: "Нельзя сменить тип: есть операции, несовместимые с новым типом.",
  // accounts, banks, currencies
  account_not_found: "Счёт не найден или недоступен.",
  account_has_transactions: "На счёте есть операции. Удалить нельзя — архивируйте его.",
  currency_mismatch: "Валюта должна совпадать с валютой счёта.",
  bank_not_found: "Банк не найден. Обновите список и выберите снова.",
  unknown_currency: "Эта валюта не поддерживается.",
  // budgets, entities
  budget_not_found: "Бюджет не найден.",
  budget_income_category: "Бюджет ограничивает расходы — выберите расходную категорию.",
  transaction_not_found: "Операция не найдена.",
  deposit_not_found: "Депозит не найден.",
  goal_not_found: "Цель не найдена.",
  invalid_date_range: "Дата окончания должна быть позже даты начала.",
  date_out_of_range: "Даты вклада должны быть в диапазоне 01.01.1900 — 31.12.2200.",
  term_too_long: "Срок вклада не может превышать 600 месяцев (50 лет).",
  duplicate: "Запись с такими данными уже существует.",
  account_name_taken: "Счёт с таким названием уже есть.",
  goal_name_taken: "Цель с таким названием уже есть.",
  invalid_amount_range: "Минимальная сумма не может быть больше максимальной.",
  period_too_long: "Слишком длинный период. Выберите период короче.",
  invalid_month: "Некорректный месяц.",
  unknown_timezone: "Неизвестный часовой пояс. Выберите другой в настройках.",
  csrf_rejected: "Запрос отклонён из соображений безопасности. Обновите страницу.",
  backend_unavailable: "Сервер недоступен. Попробуйте позже.",
  // imports
  import_not_found: "Импорт не найден.",
  import_expired: "Срок предпросмотра истёк (24 ч). Загрузите файл заново.",
  import_not_committable: "Этот импорт уже нельзя подтвердить.",
  import_not_cancellable: "Этот импорт уже нельзя отменить.",
  empty_file: "Файл пустой.",
  file_too_large: "Файл больше 5 МБ.",
  payload_too_large: "Слишком большой запрос.",
  unsupported_format: "Поддерживаются только CSV и XLSX.",
  pdf_not_supported: "PDF не поддерживается — выгрузите выписку в CSV или XLSX.",
  unreadable_file: "Кодировка файла не поддерживается (нужна UTF-8 или Windows-1251).",
  malformed_file: "Файл повреждён или имеет неверную структуру.",
  missing_columns: "Файл не похож на выписку выбранного банка. Проверьте банк или формат.",
  format_mismatch: "Файл не похож на выписку выбранного банка. Проверьте банк или формат.",
  too_many_rows: "Больше 5000 строк — разделите выписку по периодам.",
  no_transactions: "В файле не найдено операций.",
  malicious_file: "Файл отклонён по соображениям безопасности.",
  unsupported_bank: "Этот банк пока не поддерживается для импорта.",
};

const STATUS_MESSAGES: Record<number, string> = {
  0: "Нет связи с сервером. Проверьте подключение и повторите.",
  400: "Запрос не выполнен. Проверьте введённые данные.",
  401: "Сессия истекла. Войдите снова.",
  403: "Недостаточно прав для этого действия.",
  404: "Не найдено. Возможно, запись была удалена.",
  409: "Действие конфликтует с текущими данными.",
  413: "Слишком большой запрос.",
  415: "Неподдерживаемый формат.",
  422: "Проверьте правильность заполнения полей.",
  429: "Слишком много запросов. Попробуйте позже.",
  500: "Ошибка на сервере. Попробуйте позже.",
};

/** Russian text for an error; `overrides` lets a screen refine messages by code. */
export function toUserMessage(error: unknown, overrides: Record<string, string> = {}): string {
  if (!(error instanceof ApiError)) return STATUS_MESSAGES[500];
  if (overrides[error.code]) return overrides[error.code];
  if (CODE_MESSAGES[error.code]) return CODE_MESSAGES[error.code];
  if (error.status === 429 && error.retryAfterSeconds) {
    return `Слишком много запросов. Повторите через ${error.retryAfterSeconds} с.`;
  }
  if (error.status >= 500) return STATUS_MESSAGES[500];
  return STATUS_MESSAGES[error.status] ?? STATUS_MESSAGES[400];
}

/** Russian text for a single Pydantic issue (`type` is stable, `msg` is English). */
function issueMessage(issue: ValidationIssue): string {
  switch (issue.type) {
    case "missing":
      return "Обязательное поле.";
    case "greater_than":
      return "Значение должно быть больше нуля.";
    case "greater_than_equal":
      return "Значение не может быть отрицательным.";
    case "less_than_equal":
    case "less_than":
      return "Значение слишком большое.";
    case "string_too_short":
      return "Слишком короткое значение.";
    case "string_too_long":
      return "Слишком длинное значение.";
    case "string_pattern_mismatch":
      return "Неверный формат.";
    case "decimal_max_places":
      return "Не больше 2 знаков после запятой.";
    case "decimal_max_digits":
      return "Слишком большое число.";
    case "value_error":
      return "Некорректное значение.";
    default:
      return "Некорректное значение.";
  }
}

function fieldErrorsFrom(detail: ErrorBody["detail"]): FieldError[] {
  if (!Array.isArray(detail)) return [];
  return detail.map((issue) => {
    const loc = (issue.loc ?? []).filter((part) => part !== "body" && part !== "query");
    return {
      field: loc.map(String).join(".") || "_",
      message: issueMessage(issue),
      type: issue.type,
    };
  });
}

/** Build an ApiError from a non-2xx response. Never throws. */
export async function errorFromResponse(response: Response): Promise<ApiError> {
  let body: ErrorBody = {};
  try {
    body = (await response.json()) as ErrorBody;
  } catch {
    body = {};
  }
  const retryAfter = Number.parseInt(response.headers.get("retry-after") ?? "", 10);
  return new ApiError({
    status: response.status,
    code: body.code ?? `http_${response.status}`,
    requestId: body.request_id ?? response.headers.get("x-request-id"),
    fieldErrors: fieldErrorsFrom(body.detail),
    retryAfterSeconds: Number.isFinite(retryAfter) ? retryAfter : null,
  });
}

export function networkError(): ApiError {
  return new ApiError({ status: 0, code: "network_error" });
}
