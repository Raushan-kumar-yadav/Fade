#include "VulkanFrame.hpp"



VulkanFrame::VulkanFrame(DeviceContext *context, CommandPool *CommandPool)
{

    this->m_context = context;
    this->m_commandPool = CommandPool;

    m_imageAvailableSemaphore = new Semaphore(context);
    m_renderFinishedSemaphore = new Semaphore(context);
    m_inFlightFence = new Fence(context, true); 
    m_commandBuffer = new CommandBuffer(*m_commandPool,true);


}


void VulkanFrame::waitForReady()
{
    m_inFlightFence->wait();
}

void VulkanFrame::reset()
{

    m_inFlightFence->reset();
    m_commandBuffer->reset();
}


VulkanFrame::~VulkanFrame() {
    delete m_commandBuffer;
    delete m_inFlightFence;
    delete m_renderFinishedSemaphore;
    delete m_imageAvailableSemaphore;
}