/***************************************************************************
 # Copyright (c) 2015-23, NVIDIA CORPORATION. All rights reserved.
 ***************************************************************************/
#include "Testing/UnitTest.h"
#include "Utils/UI/PythonUI.h"

namespace Falcor
{
CPU_TEST(PythonUIPathToUtf8PreservesUnicode)
{
    const std::string expected = u8"C:/路径/normal_é_😀.npz";
    const std::filesystem::path path = std::filesystem::u8path(expected);
    EXPECT_EQ(python_ui::pathToUtf8(path), expected);
}
} // namespace Falcor
