export interface UserProfile {
  readonly id: string;
  readonly username: string;
  readonly email: string;
  readonly createdAt: Date;
  readonly updatedAt: Date;
  readonly settings: UserSettings;
}

export interface UserSettings {
  readonly theme: 'light' | 'dark';
  readonly notificationsEnabled: boolean;
}

export interface Habit {
  readonly id: string;
  readonly userId: string;
  readonly title: string;
  readonly description?: string;
  readonly frequency: 'daily' | 'weekly';
  readonly createdAt: Date;
  readonly updatedAt: Date;
}

export interface DailyEntry {
  readonly id: string;
  readonly userId: string;
  readonly date: Date;
  readonly habitId: string;
  readonly status: 'done' | 'skipped' | 'not-done';
}

export interface JournalRecord {
  readonly id: string;
  readonly userId: string;
  readonly date: Date;
  readonly content: string;
  readonly tags: readonly string[];
  readonly mood: 'happy' | 'neutral' | 'sad' | 'anxious';
}
