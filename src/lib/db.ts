import { getSupabaseClient } from './supabase';
import { Habit, DailyEntry } from '../types';

// Habits
export const getHabits = async (userId: string): Promise<Habit[] | null> => {
  const { data, error } = await getSupabaseClient()
    .from('habits')
    .select('*')
    .eq('userId', userId);

  if (error) {
    console.error('Error fetching habits:', error);
    return null;
  }
  return data as Habit[];
};

export const createHabit = async (habit: Omit<Habit, 'id' | 'createdAt' | 'updatedAt'>): Promise<Habit | null> => {
  const { data, error } = await getSupabaseClient()
    .from('habits')
    .insert([habit])
    .select()
    .single();

  if (error) {
    console.error('Error creating habit:', error);
    return null;
  }
  return data as Habit;
};

export const updateHabit = async (id: string, updates: Partial<Omit<Habit, 'id' | 'userId' | 'createdAt' | 'updatedAt'>>): Promise<Habit | null> => {
  const { data, error } = await getSupabaseClient()
    .from('habits')
    .update(updates)
    .eq('id', id)
    .select()
    .single();

  if (error) {
    console.error('Error updating habit:', error);
    return null;
  }
  return data as Habit;
};

export const deleteHabit = async (id: string): Promise<boolean> => {
  const { error } = await getSupabaseClient()
    .from('habits')
    .delete()
    .eq('id', id);

  if (error) {
    console.error('Error deleting habit:', error);
    return false;
  }
  return true;
};

// Entries
export const getEntries = async (userId: string, date: Date): Promise<DailyEntry[] | null> => {
  const { data, error } = await getSupabaseClient()
    .from('daily_entries')
    .select('*')
    .eq('userId', userId)
    .eq('date', date.toISOString());

  if (error) {
    console.error('Error fetching entries:', error);
    return null;
  }
  return data as DailyEntry[];
};

export const createDailyEntry = async (entry: Omit<DailyEntry, 'id'>): Promise<DailyEntry | null> => {
  const { data, error } = await getSupabaseClient()
    .from('daily_entries')
    .insert([entry])
    .select()
    .single();

  if (error) {
    console.error('Error creating daily entry:', error);
    return null;
  }
  return data as DailyEntry;
};

export const updateDailyEntry = async (id: string, updates: Partial<Omit<DailyEntry, 'id' | 'userId'>>): Promise<DailyEntry | null> => {
  const { data, error } = await getSupabaseClient()
    .from('daily_entries')
    .update(updates)
    .eq('id', id)
    .select()
    .single();

  if (error) {
    console.error('Error updating daily entry:', error);
    return null;
  }
  return data as DailyEntry;
};

export const deleteDailyEntry = async (id: string): Promise<boolean> => {
  const { error } = await getSupabaseClient()
    .from('daily_entries')
    .delete()
    .eq('id', id);

  if (error) {
    console.error('Error deleting daily entry:', error);
    return false;
  }
  return true;
};
