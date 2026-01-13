"""Japanese messages for the application (日本語メッセージ)"""

MESSAGES_JA = {
    # ============================================
    # Authentication Messages (認証メッセージ)
    # ============================================
    "LOGIN_SUCCESS": "ログインに成功しました",
    "LOGOUT_SUCCESS": "ログアウトしました",
    "REGISTRATION_SUCCESS": "登録が完了しました",
    "TOKEN_REFRESHED": "トークンを更新しました",
    "PASSWORD_CHANGED": "パスワードを変更しました",
    "INVALID_CREDENTIALS": "電話番号またはパスワードが正しくありません",
    "INVALID_EMAIL_PASSWORD": "メールアドレスまたはパスワードが正しくありません",
    "ACCOUNT_INACTIVE": "アカウントが無効です",
    "SESSION_REVOKED": "セッションが無効です。再度ログインしてください",
    "TOKEN_INVALID": "認証情報を確認できませんでした",
    "TOKEN_REVOKED": "トークンが無効です。再度ログインしてください",
    "INSUFFICIENT_PERMISSIONS": "権限が不足しています",
    # ============================================
    # User Management (ユーザー管理)
    # ============================================
    "USER_NOT_FOUND": "ユーザーが見つかりません",
    "USERS_RETRIEVED_SUCCESS": "ユーザー一覧を取得しました",
    "NO_USERS_FOUND": "ユーザーが見つかりません",
    "USER_DETAIL_RETRIEVED": "ユーザー詳細を取得しました",
    "PROFILE_RETRIEVED": "プロフィール情報を取得しました",
    "NAME_REQUIRED": "名前は必須です",
    "NAME_EMPTY": "名前を入力してください",
    "PHONE_IN_USE": "この電話番号は既に使用されています",
    "PHONE_REGISTERED": "この電話番号は既に登録されています",
    "EMAIL_IN_USE": "このメールアドレスは既に使用されています",
    "EMAIL_REGISTERED": "このメールアドレスは既に登録されています",
    "LINE_REGISTERED": "このLINEアカウントは既に登録されています",
    "NO_PASSWORD_ACCOUNT": "このアカウントはパスワードで作成されていません",
    "INCORRECT_PASSWORD": "現在のパスワードが正しくありません",
    "INVALID_PHONE_FORMAT": "電話番号の形式が無効です。インドの電話番号（6-9で始まる10桁）または日本の電話番号（070/080/090で始まる11桁）を入力してください",
    # ============================================
    # LINE Integration (LINE連携)
    # ============================================
    "LINE_TOKEN_INVALID": "LINEアクセストークンが無効です",
    "LINE_PROFILE_FAILED": "LINEプロフィールの取得に失敗しました",
    "LINE_TIMEOUT": "LINE APIがタイムアウトしました。ネットワーク接続を確認して、再度お試しください",
    "LINE_CONNECTION_FAILED": "LINE APIへの接続に失敗しました: {error}",
    # ============================================
    # Appointments (予約)
    # ============================================
    "APPOINTMENT_BOOKED": "予約が完了しました",
    "APPOINTMENT_CANCELLED": "予約をキャンセルしました",
    "APPOINTMENT_UPDATED": "予約ステータスを更新しました",
    "APPOINTMENT_RETRIEVED": "予約情報を取得しました",
    "APPOINTMENTS_RETRIEVED": "予約一覧を取得しました",
    "APPOINTMENT_STATS_RETRIEVED": "予約統計情報を取得しました",
    "APPOINTMENT_NOT_FOUND": "予約ID {appointment_id} が見つかりません",
    "TIME_SLOT_FULL": "この時間帯は満席です",
    "INVALID_STATUS_TRANSITION": "予約ステータスを {current} から {new} に変更できません",
    "CANNOT_CANCEL_COMPLETED": "完了済みの予約はキャンセルできません",
    "SLOT_UNAVAILABLE": "選択された時間帯は利用できなくなりました",
    "SERVICE_REQUIRED": "少なくとも1つのサービスを選択してください",
    "INVALID_SERVICE": "無効なサービスコード: {code}",
    "PAST_SLOT": "過去の時間帯には予約できません",
    # ============================================
    # Services (サービス)
    # ============================================
    "SERVICE_CREATED": "サービスを作成しました",
    "SERVICE_UPDATED": "サービスを更新しました",
    "SERVICE_DELETED": "サービスを削除しました",
    "SERVICE_RETRIEVED": "サービス情報を取得しました",
    "SERVICES_RETRIEVED": "サービス一覧を取得しました",
    "SERVICE_ORDER_UPDATED": "サービスの表示順序を更新しました",
    "SERVICE_NOT_FOUND": "サービスコード {code} が見つかりません",
    "CATEGORY_NOT_FOUND_FOR_SERVICE": "カテゴリーコード {category_code} が見つかりません",
    "CSV_UPLOAD_SUCCESS": "CSVファイルをアップロードしました",
    "FILE_MUST_BE_CSV": "CSVファイルを選択してください",
    "DB_CONSTRAINT_VIOLATION": "データベース制約違反です。データを確認してください",
    "CSV_UPLOAD_ERROR": "CSVアップロード中にエラーが発生しました",
    # ============================================
    # Categories (カテゴリー)
    # ============================================
    "CATEGORY_CREATED": "カテゴリーを作成しました",
    "CATEGORY_UPDATED": "カテゴリーを更新しました",
    "CATEGORY_DELETED": "カテゴリーを削除しました",
    "CATEGORY_RETRIEVED": "カテゴリー情報を取得しました",
    "CATEGORIES_RETRIEVED": "カテゴリー一覧を取得しました",
    "PUBLIC_CATEGORIES_RETRIEVED": "公開カテゴリー一覧を取得しました",
    "CATEGORY_ORDER_UPDATED": "カテゴリーの表示順序を更新しました",
    "CATEGORY_NOT_FOUND": "カテゴリーコード {code} が見つかりません",
    "CATEGORY_HAS_SERVICES": "{count}個の有効なサービスが含まれているため、カテゴリーを削除できません。先にサービスを削除してください",
    # ============================================
    # Time Slots (時間帯)
    # ============================================
    "TIME_SLOT_CREATED": "時間帯を作成しました",
    "TIME_SLOT_UPDATED": "時間帯を更新しました",
    "TIME_SLOT_DELETED": "時間帯を削除しました",
    "TIME_SLOT_RETRIEVED": "時間帯情報を取得しました",
    "TIME_SLOTS_RETRIEVED": "時間帯一覧を取得しました",
    "AVAILABLE_SLOTS_RETRIEVED": "利用可能な時間帯一覧を取得しました",
    "BULK_CREATION_COMPLETED": "一括作成が完了しました",
    "BULK_CREATION_SUMMARY": "{created}個の時間帯を作成し、{skipped}日をスキップしました",
    "TIME_SLOT_NOT_FOUND": "時間帯ID {time_slot_id} が見つかりません",
    "OVERLAPPING_SLOT": "{date} の {start_time} から {end_time} に重複する時間帯が存在します",
    "CANNOT_UPDATE_DELETED": "削除済みの時間帯は更新できません。is_active=trueに設定して有効化してください",
    "START_BEFORE_END": "新しい開始時刻は既存の終了時刻 ({end_time}) より前である必要があります",
    "END_AFTER_START": "新しい終了時刻は既存の開始時刻 ({start_time}) より後である必要があります",
    "CAPACITY_TOO_LOW": "定員を{capacity}に減らすことはできません。現在の予約数: {bookings}",
    "CANNOT_DELETE_WITH_BOOKINGS": "{bookings}件の予約があるため、時間帯を削除できません。先に全ての予約をキャンセルしてください",
    # ============================================
    # Admin & Sessions (管理者とセッション)
    # ============================================
    "ADMIN_PROFILE_RETRIEVED": "管理者プロフィールを取得しました",
    "INACTIVE_ADMIN": "管理者アカウントが無効です",
    "INACTIVE_USER": "ユーザーアカウントが無効です",
    "OTP_SENT": "メールアドレスが存在する場合、OTPを送信しました",
    "OTP_INVALID": "OTPが無効または期限切れです",
    "OTP_EXPIRED": "OTPの有効期限が切れています",
    "OTP_TOO_MANY_ATTEMPTS": "試行回数が多すぎます",
    "OTP_VERIFIED": "OTPの確認が完了しました",
    "PASSWORD_RESET_SUCCESS": "パスワードをリセットしました",
    "SESSIONS_RETRIEVED": "セッション一覧を取得しました",
    "SESSION_REVOKED_SUCCESS": "セッションを無効化しました",
    "SESSIONS_REVOKED": "{count}個のセッションを無効化しました",
    "LOGIN_HISTORY_RETRIEVED": "ログイン履歴を取得しました",
    # ============================================
    # System Messages (システムメッセージ)
    # ============================================
    "INTERNAL_ERROR": "内部エラーが発生しました",
    "VALIDATION_ERROR": "入力値エラー",
    "NOT_FOUND": "リソースが見つかりません",
    "UNAUTHORIZED": "認証が必要です",
    "FORBIDDEN": "アクセスが拒否されました",
}
