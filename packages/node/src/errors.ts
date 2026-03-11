export class VergeError extends Error {
  constructor(message: string) {
    super(message);
    this.name = new.target.name;
  }
}

export class VergeConfigError extends VergeError {}
export class VergeAuthError extends VergeError {}
export class VergeNotFoundError extends VergeError {}
export class VergeConflictError extends VergeError {}
export class VergeValidationError extends VergeError {}
export class VergeServerError extends VergeError {}
