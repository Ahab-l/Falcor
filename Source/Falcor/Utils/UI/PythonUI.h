/***************************************************************************
 # Copyright (c) 2015-23, NVIDIA CORPORATION. All rights reserved.
 #
 # Redistribution and use in source and binary forms, with or without
 # modification, are permitted provided that the following conditions
 # are met:
 #  * Redistributions of source code must retain the above copyright
 #    notice, this list of conditions and the following disclaimer.
 #  * Redistributions in binary form must reproduce the above copyright
 #    notice, this list of conditions and the following disclaimer in the
 #    documentation and/or other materials provided with the distribution.
 #  * Neither the name of NVIDIA CORPORATION nor the names of its
 #    contributors may be used to endorse or promote products derived
 #    from this software without specific prior written permission.
 #
 # THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS "AS IS" AND ANY
 # EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
 # IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR
 # PURPOSE ARE DISCLAIMED.  IN NO EVENT SHALL THE COPYRIGHT OWNER OR
 # CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL,
 # EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING, BUT NOT LIMITED TO,
 # PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES; LOSS OF USE, DATA, OR
 # PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON ANY THEORY
 # OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
 # (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
 # OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
 **************************************************************************/
#pragma once

#include "Core/Object.h"

#include <imgui.h>

#include <string>
#include <string_view>
#include <functional>
#include <filesystem>
#include <algorithm>
#include <stdexcept>
#include <vector>

namespace Falcor
{
namespace python_ui
{

/** Convert a native filesystem path to the UTF-8 representation expected by Python. */
FALCOR_API std::string pathToUtf8(const std::filesystem::path& path);

/// Base class for Python UI widgets.
/// Widgets own their children.
class Widget : public Object
{
    FALCOR_OBJECT(Widget)
public:
    Widget(Widget* parent) : m_parent(parent)
    {
        if (m_parent)
        {
            m_parent->check_tree_mutation();
            m_parent->m_children.push_back(ref<Widget>(this));
        }
    }

    virtual ~Widget() { clear_children(); }

    Widget* get_parent() { return m_parent; }
    const Widget* get_parent() const { return m_parent; }
    void set_parent(Widget* parent) { m_parent = parent; }

    const std::vector<ref<Widget>>& get_children() const { return m_children; }

    /// Remove this widget from its owning parent. Idempotent; call between UI
    /// frames. Draw callbacks must enqueue tree mutations for a frame listener.
    void detach()
    {
        check_tree_mutation();
        if (!m_parent)
            return;
        ref<Widget> keep_alive(this);
        auto& children = m_parent->m_children;
        m_parent = nullptr;
        children.erase(
            std::remove_if(children.begin(), children.end(), [this](const auto& child) { return child.get() == this; }), children.end()
        );
    }

    /// Release owned children while Python is still alive, including on shutdown.
    void clear_children()
    {
        for (const auto& child : m_children)
            if (child->m_parent == this)
                child->m_parent = nullptr;
        m_children.clear();
    }

    bool get_visible() const { return m_visible; }
    void set_visible(bool visible) { m_visible = visible; }

    bool get_enabled() const { return m_enabled; }
    void set_enabled(bool enabled) { m_enabled = enabled; }

    virtual void render()
    {
        if (m_visible)
        {
            struct RenderScope
            {
                bool& rendering;
                RenderScope(bool& value) : rendering(value) { rendering = true; }
                ~RenderScope() { rendering = false; }
            } scope(m_rendering);
            for (const auto& child : m_children)
                child->render();
        }
    }

protected:
    bool is_tree_rendering() const
    {
        for (const Widget* widget = this; widget; widget = widget->m_parent)
            if (widget->m_rendering)
                return true;
        return false;
    }

    void check_tree_mutation() const
    {
        if (is_tree_rendering())
            throw std::runtime_error("PythonUI tree mutation during render is not supported; enqueue it for the next frame listener.");
    }

    Widget* m_parent;
    std::vector<ref<Widget>> m_children;
    bool m_visible{true};
    bool m_enabled{true};
    bool m_rendering{false};
};

/// This is the main widget that represents the screen.
/// It is intended to be used as the parent for \c Window widgets.
class Screen : public Widget
{
    FALCOR_OBJECT(Screen)
public:
    Screen() : Widget(nullptr) {}

    virtual void render() override { Widget::render(); }
};

// The widgets are implemented in the C++ file as they are only exposed to Python.

} // namespace python_ui
} // namespace Falcor
