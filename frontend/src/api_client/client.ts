import axios from 'axios';

const BASE_URL = 'http://localhost:8000';

export async function sendQuery(query: string, context: any): Promise<string> {
    try {
        const response = await axios.post(`${BASE_URL}/chat`, { query, context });
        return response.data.result;
    } catch (error) {
        console.error(error);
        return "Error connecting to backend.";
    }
}

export async function fetchCompletions(prompt: string): Promise<string> {
    try {
        const response = await axios.post(`${BASE_URL}/completion`, { prompt });
        return response.data.text;
    } catch (error) {
        console.error(error);
        return "";
    }
}

export async function confirmCommand(action: 'accept' | 'reject'): Promise<string> {
    try {
        const response = await axios.post(`${BASE_URL}/command-confirm`, { action });
        return response.data.result;
    } catch (error) {
        return "Error executing command.";
    }
}