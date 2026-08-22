 #include "ThreadPool.hpp"

void ThreadPool::workderLoop()
{
    while (true)
    {

        std::function<void()> job;

        {
            std::unique_lock<std::mutex> lock(m_mutex);
            m_cv.wait(lock,[this](){return !m_jobs.empty() || m_stop.load();});

            if(m_jobs.empty() && m_stop) return;
            job = std::move(m_jobs.front());
            m_jobs.pop_front();
        }

        job();

    }
    
}



ThreadPool::ThreadPool(int threadCount) : m_threadCound(threadCount)
{
    for(int i = 0 ; i < m_threadCound;++i) {
        m_workers.emplace_back([this](){workderLoop();});
    }
}

ThreadPool::~ThreadPool()
{
    m_stop = true;
    m_cv.notify_all();
    for (auto& t : m_workers)
        if (t.joinable()) t.join();

}


void ThreadPool::submitWork(std::function<void()> job)
{
    if(job){
        {
            std::lock_guard<std::mutex> lock(m_mutex);
            m_jobs.push_back(job);
        }

        m_cv.notify_one();
    }
}



