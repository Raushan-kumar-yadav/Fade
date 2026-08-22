#pragma once
#include <iostream>
#include <thread>
#include <vector>
#include <deque>
#include <functional>
#include <mutex>

class ThreadPool
{
private:

void workderLoop();
int m_threadCound;
std::vector<std::thread> m_workers; 
std::deque<std::function<void()>> m_jobs;
std::mutex m_mutex;
std::condition_variable m_cv;
std::atomic<bool> m_stop{false};

public:
    ThreadPool(int threadCount);
    ~ThreadPool();

    void submitWork(std::function<void()> job);
};


