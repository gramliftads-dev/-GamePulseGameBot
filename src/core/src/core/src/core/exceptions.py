GamePulseException
├── ConfigurationError
│   └── EnvironmentVariableError
├── DatabaseError
│   ├── DatabaseConnectionError
│   ├── DatabaseQueryError
│   ├── RecordNotFoundError
│   └── RecordAlreadyExistsError
├── RedisError
│   ├── RedisConnectionError
│   └── RedisOperationError
├── BotError
│   ├── BotHandlerError
│   └── BotCallbackError
├── GameError
│   ├── GameSessionError
│   │   ├── GameSessionExpiredError
│   │   └── GameSessionNotFoundError
│   ├── GameValidationError
│   │   └── InvalidScoreError
│   ├── GameNotAvailableError
│   └── GameAlreadyStartedError
├── UserError
│   ├── UserNotFoundError
│   ├── UserBannedError
│   ├── UserNotRegisteredError
│   └── UserAlreadyExistsError
├── AuthenticationError
│   ├── UnauthorizedError
│   └── AdminRequiredError
├── RateLimitError
│   └── GameRateLimitError
├── AntiCheatError
│   ├── SuspiciousActivityError
│   └── ScoreTamperingError
├── ReferralError
│   ├── InvalidReferralCodeError
│   ├── SelfReferralError
│   └── ReferralLimitExceededError
├── FriendChallengeError
│   ├── ChallengeNotFoundError
│   ├── ChallengeExpiredError
│   └── ChallengeAlreadyCompletedError
├── DailyChallengeError
│   └── ChallengeAlreadyCompletedError
├── AchievementError
│   ├── AchievementNotFoundError
│   └── AchievementAlreadyUnlockedError
├── NotificationError
└── APIError
    ├── APINotFoundError
    └── APIValidationError
